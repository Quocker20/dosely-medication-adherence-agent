import { useRef } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  length?: number;
  autoFocus?: boolean;
  disabled?: boolean;
  id?: string;
}

export default function PinDotInput({
  value,
  onChange,
  length = 6,
  autoFocus = false,
  disabled = false,
  id,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="pin-dots" onClick={() => inputRef.current?.focus()}>
      <input
        ref={inputRef}
        id={id}
        className="pin-dots-input"
        type="password"
        autoComplete="current-password"
        inputMode="numeric"
        autoFocus={autoFocus}
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, length))}
        aria-label="Mã PIN"
      />
      {Array.from({ length }, (_, index) => (
        <span key={index} className={`pin-dot${index < value.length ? " filled" : ""}`} aria-hidden="true" />
      ))}
    </div>
  );
}
