package com.dosely.app.di

import com.google.gson.FieldNamingPolicy
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.dosely.app.BuildConfig
import com.dosely.app.data.remote.ApiConfig
import com.dosely.app.data.remote.AuthTokenResponseDto
import com.dosely.app.data.remote.RefreshTokenRequestDto
import com.dosely.app.data.remote.DoselyApiService
import com.dosely.app.data.repository.AuthSession
import com.dosely.app.data.repository.SessionStore
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Qualifier
import javax.inject.Singleton
import kotlinx.coroutines.runBlocking
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class RefreshClient

/** Adds the current access token only to endpoints that require authentication. */
class BearerTokenInterceptor(
    private val sessionStore: SessionStore,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        if (original.isPublicAuthRequest()) return chain.proceed(original)

        val session = sessionStore.session.value
        val existingAuthorization = original.header(AUTHORIZATION)
        val existingToken = original.bearerToken()
        if (existingAuthorization != null && existingToken == null) return chain.proceed(original)
        val token = existingToken ?: session?.accessToken
        if (token == null) return chain.proceed(original)

        val request = original.newBuilder().apply {
            if (existingToken == null) header(AUTHORIZATION, "Bearer $token")
            session?.takeIf { it.accessToken == token }?.let { matchingSession ->
                tag(RequestSession::class.java, RequestSession(matchingSession))
            }
        }.build()
        return chain.proceed(request)
    }
}

fun interface TokenRefreshGateway {
    /** Returns null when the refresh response is unsuccessful or has no token data. */
    fun refresh(refreshToken: String): AuthTokenResponseDto?
}

class RetrofitTokenRefreshGateway(
    private val api: DoselyApiService,
) : TokenRefreshGateway {
    override fun refresh(refreshToken: String): AuthTokenResponseDto? = runBlocking {
        val envelope = api.refreshToken(RefreshTokenRequestDto(refreshToken))
        envelope.data?.takeIf { envelope.success }
    }
}

/**
 * Rotates an expired access token once and replays the rejected request once.
 *
 * Refresh calls use a dedicated Retrofit client without this authenticator,
 * which removes the possibility of recursive refresh. The synchronized block
 * also prevents concurrent 401 responses from rotating the same refresh token
 * more than once.
 */
class SessionAuthenticator(
    private val sessionStore: SessionStore,
    private val refreshGateway: TokenRefreshGateway,
) : Authenticator {
    private val refreshLock = Any()

    override fun authenticate(route: Route?, response: Response): Request? {
        if (response.responseCount() >= MAX_RESPONSE_COUNT) return null
        if (response.request.isNonRefreshableAuthRequest()) return null

        val failedAccessToken = response.request.bearerToken() ?: return null
        return synchronized(refreshLock) {
            val sessionBeforeRefresh = sessionStore.session.value ?: return@synchronized null

            // A concurrent request already refreshed the session. Reuse its
            // token instead of rotating the single-use refresh token again.
            if (sessionBeforeRefresh.accessToken != failedAccessToken) {
                val requestPatientId = response.request
                    .tag(RequestSession::class.java)
                    ?.session
                    ?.patientId
                if (requestPatientId != null && requestPatientId != sessionBeforeRefresh.patientId) {
                    return@synchronized null
                }
                return@synchronized response.request.withBearerToken(sessionBeforeRefresh.accessToken)
            }

            val refreshed = try {
                refreshGateway.refresh(sessionBeforeRefresh.refreshToken)
            } catch (_: Exception) {
                null
            }
            if (refreshed == null || refreshed.user.id != sessionBeforeRefresh.patientId) {
                sessionStore.clearIfCurrent(sessionBeforeRefresh)
                return@synchronized null
            }

            val renewedSession = AuthSession(
                accessToken = refreshed.accessToken,
                refreshToken = refreshed.refreshToken,
                patientId = refreshed.user.id,
                mustChangePassword = refreshed.mustChangePassword,
                needOnboarding = refreshed.needOnboarding,
                phone = refreshed.user.phone,
            )
            try {
                if (!sessionStore.updateIfCurrent(sessionBeforeRefresh, renewedSession)) {
                    return@synchronized null
                }
            } catch (_: Exception) {
                sessionStore.clearIfCurrent(sessionBeforeRefresh)
                return@synchronized null
            }
            response.request.withBearerToken(renewedSession.accessToken)
        }
    }
}

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideLoggingInterceptor(): HttpLoggingInterceptor =
        HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                // Không log body vì có thể chứa dữ liệu sức khỏe/triệu chứng.
                HttpLoggingInterceptor.Level.BASIC
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }

    @Provides
    @Singleton
    @RefreshClient
    fun provideRefreshOkHttpClient(logging: HttpLoggingInterceptor): OkHttpClient =
        OkHttpClient.Builder()
            .addInterceptor(logging)
            .build()

    @Provides
    @Singleton
    @RefreshClient
    fun provideRefreshRetrofit(
        @RefreshClient client: OkHttpClient,
        gson: Gson,
    ): Retrofit = Retrofit.Builder()
        .baseUrl(ApiConfig.BASE_URL)
        .client(client)
        .addConverterFactory(GsonConverterFactory.create(gson))
        .build()

    @Provides
    @Singleton
    @RefreshClient
    fun provideRefreshApiService(@RefreshClient retrofit: Retrofit): DoselyApiService =
        retrofit.create(DoselyApiService::class.java)

    @Provides
    @Singleton
    fun provideTokenRefreshGateway(
        @RefreshClient api: DoselyApiService,
    ): TokenRefreshGateway = RetrofitTokenRefreshGateway(api)

    @Provides
    @Singleton
    fun provideOkHttpClient(
        sessionStore: SessionStore,
        logging: HttpLoggingInterceptor,
        refreshGateway: TokenRefreshGateway,
    ): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(BearerTokenInterceptor(sessionStore))
        .authenticator(SessionAuthenticator(sessionStore, refreshGateway))
        .addInterceptor(logging)
        .build()

    @Provides
    @Singleton
    fun provideGson(): Gson =
        // Backend (FastAPI/Pydantic) trả JSON snake_case — map thẳng sang field camelCase.
        GsonBuilder()
            .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
            .create()

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient, gson: Gson): Retrofit =
        Retrofit.Builder()
            .baseUrl(ApiConfig.BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()

    @Provides
    @Singleton
    fun provideDoselyApiService(retrofit: Retrofit): DoselyApiService =
        retrofit.create(DoselyApiService::class.java)
}

private const val AUTHORIZATION = "Authorization"
private const val MAX_RESPONSE_COUNT = 2

private data class RequestSession(val session: AuthSession)

private fun Request.isPublicAuthRequest(): Boolean =
    url.encodedPath.endsWith("/auth/login") || url.encodedPath.endsWith("/auth/refresh")

private fun Request.isNonRefreshableAuthRequest(): Boolean =
    isPublicAuthRequest() || url.encodedPath.endsWith("/auth/logout")

private fun Request.bearerToken(): String? {
    val value = header(AUTHORIZATION) ?: return null
    if (!value.startsWith("Bearer ", ignoreCase = true)) return null
    return value.substringAfter(' ').takeIf(String::isNotBlank)
}

private fun Request.withBearerToken(token: String): Request = newBuilder()
    .header(AUTHORIZATION, "Bearer $token")
    .build()

private fun Response.responseCount(): Int {
    var count = 1
    var current = priorResponse
    while (current != null) {
        count += 1
        current = current.priorResponse
    }
    return count
}
