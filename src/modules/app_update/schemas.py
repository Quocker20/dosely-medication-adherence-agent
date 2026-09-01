from pydantic import BaseModel, ConfigDict, Field


class LatestAppVersionResponse(BaseModel):
    """The one release a sideloaded Android client should compare against."""

    model_config = ConfigDict(populate_by_name=True)

    version_code: int = Field(alias="versionCode")
    version_name: str = Field(alias="versionName")
    download_url: str = Field(alias="downloadUrl")
