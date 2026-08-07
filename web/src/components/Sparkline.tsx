interface Props {
  values: number[];
  tone: "ok" | "warn" | "crit";
  width?: number;
  height?: number;
}

/** Đường tuân thủ 7 ngày: vùng nền nhạt, đường đậm, chấm nhấn ở điểm cuối. */
export default function Sparkline({ values, tone, width = 116, height = 26 }: Props) {
  if (values.length < 2) return null;

  const pad = 2;
  const min = 30;
  const max = 100;

  const points = values.map((value, index) => {
    const x = pad + (index * (width - pad * 2)) / (values.length - 1);
    const raw = height - pad - ((value - min) / (max - min)) * (height - pad * 2);
    return [x, Math.max(pad, Math.min(height - pad, raw))] as const;
  });

  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const area = `${line} L${last[0].toFixed(1)} ${height - pad} L${points[0][0].toFixed(1)} ${height - pad} Z`;

  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <path d={area} fill={`var(--${tone}-soft)`} />
      <path d={line} fill="none" stroke={`var(--${tone})`} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0].toFixed(1)} cy={last[1].toFixed(1)} r="2.6" fill={`var(--${tone})`} />
    </svg>
  );
}
