interface Props {
  onLogin: () => void;
}

/**
 * Cổng vào công khai — hiện trước khi đăng nhập, dùng chung cho cả 3 role
 * (bác sĩ/admin/bệnh nhân). Vào đúng portal nào do App.tsx quyết định sau khi
 * có session, trang này không biết và không cần biết role.
 */
export default function HomePage({ onLogin }: Props) {
  return (
    <div className="home-wrap">
      <div className="home-card">
        <div className="brand home-brand">
          <div className="brand-mark">Rx</div>
          <div>
            <div className="brand-name">RemindRx</div>
            <div className="brand-sub">Nhắc thuốc & theo dõi tuân thủ điều trị</div>
          </div>
        </div>

        <p className="home-tagline">
          Nền tảng hỗ trợ bệnh nhân mạn tính uống thuốc đúng giờ, đúng liều — và giúp bác sĩ theo dõi
          tuân thủ điều trị theo thời gian thực.
        </p>

        <button className="btn primary home-cta" onClick={onLogin}>
          Đăng nhập
        </button>

        <p className="rail-note home-foot">Mọi thay đổi phác đồ đều cần bác sĩ duyệt (HITL).</p>
      </div>
    </div>
  );
}
