import { useEffect, useState } from "react";

import Icon from "./Icon";
import type { DoseReminder } from "./useFcmReminders";

interface Props {
  reminders: DoseReminder[];
  onDismiss: (id: string) => void;
}

interface ItemProps {
  reminder: DoseReminder;
  onDismiss: (id: string) => void;
}

function DoseReminderItem({ reminder, onDismiss }: ItemProps) {
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setLeaving(true);
      setTimeout(() => onDismiss(reminder.id), 220);
    }, 11780);

    return () => clearTimeout(timer);
  }, [reminder.id, onDismiss]);

  const handleClose = () => {
    setLeaving(true);
    setTimeout(() => onDismiss(reminder.id), 220);
  };

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`dose-reminder-card ${leaving ? "leaving" : ""}`}
    >
      <div className="dose-reminder-icon" aria-hidden="true">
        <Icon name="bell" size={20} />
      </div>
      <div className="dose-reminder-content">
        <strong className="dose-reminder-title">{reminder.title}</strong>
        <p className="dose-reminder-body">{reminder.body}</p>
      </div>
      <button
        type="button"
        className="dose-reminder-close"
        onClick={handleClose}
        aria-label="Đóng thông báo"
      >
        &times;
      </button>
    </div>
  );
}

export default function DoseReminderStack({ reminders, onDismiss }: Props) {
  if (reminders.length === 0) return null;

  return (
    <div className="dose-reminder-stack" aria-label="Thông báo nhắc thuốc">
      {reminders.map((reminder) => (
        <DoseReminderItem
          key={reminder.id}
          reminder={reminder}
          onDismiss={onDismiss}
        />
      ))}
    </div>
  );
}
