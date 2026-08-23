import { useCallback, useEffect, useState } from "react";

import { api } from "../../../api";
import type { AuditLog, PageResponse } from "../../../types";
import { formatDateTime } from "../../../utils/labels";
import { ErrorPanel, errorLines } from "./ErrorPanel";

export default function AuditLogsView({ toast }: { toast: (message: string) => void }) {
  const [page, setPage] = useState(1);
  const [actorId, setActorId] = useState("");
  const [entityType, setEntityType] = useState("");
  const [data, setData] = useState<PageResponse<AuditLog> | null>(null);
  const [error, setError] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try { setData(await api.adminAuditLogs({ page, size: 20, actorId: actorId.trim() || undefined, entityType: entityType.trim() || undefined })); }
    catch (cause) { setError(errorLines(cause)); }
  }, [actorId, entityType, page]);
  useEffect(() => { load().catch(() => undefined); }, [load]);

  return (
    <section className="view">
      {error && <ErrorPanel lines={error} onRetry={() => load().catch(() => undefined)} />}
      <div className="card">
        <div className="card-head"><h2>Audit logs</h2><div className="spacer" /><button className="btn sm" onClick={() => load().then(() => toast("Đã tải audit logs")).catch(() => undefined)}>↻ Làm mới</button></div>
        <div className="card-body">
          <div className="admin-toolbar"><input placeholder="Actor UUID" value={actorId} onChange={(event) => { setPage(1); setActorId(event.target.value); }} /><input placeholder="Entity type, ví dụ DOCTOR_PROFILE" value={entityType} onChange={(event) => { setPage(1); setEntityType(event.target.value); }} /><button className="btn sm" onClick={() => load().catch(() => undefined)}>Lọc</button></div>
          <div className="table-wrap"><table><thead><tr><th>Thời gian</th><th>Action</th><th>Entity</th><th>Actor</th><th>IP</th><th>Chi tiết</th></tr></thead><tbody>{data?.content.map((log) => <tr key={log.id}><td>{formatDateTime(log.created_at)}</td><td><span className="pill accent">{log.action}</span></td><td>{log.entity_type}<br /><span className="rail-note">{log.entity_id ?? "—"}</span></td><td className="mono">{log.actor_user_id ?? "—"}</td><td>{log.ip_address ?? "—"}</td><td><details><summary>Xem JSON</summary><pre className="admin-json">{JSON.stringify({ old_values: log.old_values, new_values: log.new_values }, null, 2)}</pre></details></td></tr>)}</tbody></table></div>
          {data && data.content.length === 0 && <p className="empty">Chưa có audit log phù hợp.</p>}
          {data && <div className="row-actions pagination"><button className="btn sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>← Trước</button><span className="rail-note">Trang {page} / {Math.max(data.total_pages, 1)}</span><button className="btn sm" disabled={data.last} onClick={() => setPage((value) => value + 1)}>Sau →</button></div>}
        </div>
      </div>
    </section>
  );
}
