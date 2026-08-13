import type { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
}

/** Nhắc ranh giới HITL ngay tại màn hình bác sĩ đang thao tác. */
export default function GuardBanner({ title, children }: Props) {
  return (
    <div className="guard">
      <svg
        width="17"
        height="17"
        viewBox="0 0 16 16"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.6"
        style={{ flex: "none", marginTop: 2 }}
        aria-hidden="true"
      >
        <path d="M8 1.8 13.5 4v4c0 3-2.3 5.4-5.5 6.2C4.8 13.4 2.5 11 2.5 8V4z" strokeLinejoin="round" />
        <path d="M5.9 8.1 7.3 9.5l3-3.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="guard-body">
        <div className="guard-title">{title}</div>
        <ul>{children}</ul>
      </div>
    </div>
  );
}
