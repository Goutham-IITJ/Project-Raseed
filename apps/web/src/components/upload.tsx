"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSession } from "./app-provider";
import { Icon } from "./icon";
import { ErrorState, Status } from "./ui";
import { validateReceipt } from "@/lib/client";
import { useResource } from "@/lib/use-resource";
import type { Receipt } from "@/lib/types";

export function ReceiptProgress({ initial, onNavigate }: { initial: Receipt; onNavigate?: () => void }) {
  const { api, demo } = useSession();
  const resource = useResource(signal => api.receipt(initial.id, signal), initial.id);
  const receipt = resource.data ?? initial;
  const [polling, setPolling] = useState(true);
  const terminal = receipt.status === "PROCESSED" || receipt.status === "NEEDS_REVIEW";
  const refresh = resource.refresh;
  useEffect(() => {
    if (terminal || !polling) return;
    let attempts = 0;
    const timer = setInterval(() => { refresh(); attempts += 1; if (attempts >= 40) { clearInterval(timer); setPolling(false); } }, 3000);
    return () => clearInterval(timer);
  }, [terminal, polling, refresh]);
  const done = receipt.status === "PROCESSED";
  return <div className="receipt-progress"><CaptureSteps stage={done ? 4 : receipt.status === "NEEDS_REVIEW" ? 3 : receipt.status === "PROCESSING" ? 2 : 1} failed={receipt.status === "FAILED"} /><span className={"success-symbol " + (done ? "" : "processing-symbol")}><Icon name={done ? "check" : receipt.status === "NEEDS_REVIEW" || receipt.status === "FAILED" ? "warning" : "receipt"} size={30} /></span><Status value={receipt.status} /><h3>{done ? "Purchase ready" : receipt.status === "NEEDS_REVIEW" ? "Needs review" : receipt.status === "FAILED" ? "Processing failed" : "Processing receipt"}</h3><p>{done ? "Your purchase is ready to explore." : receipt.failure_message ?? "Your receipt is uploaded and queued for processing."}</p><p className="caption">{receipt.original_filename}</p>{demo && !done && <p className="help-text">Local demo: uploads stay queued.</p>}{receipt.status === "NEEDS_REVIEW" && <p className="help-text">Automatic processing couldn’t confirm the details. Your original is saved; review requires support at this stage.</p>}{!polling && !terminal && <p className="help-text">This is taking longer than usual. You can leave this window and check processing in Purchases.</p>}{resource.error && <ErrorState message={resource.error} retry={resource.refresh} />}<div className="actions">{done && receipt.purchase_id ? <Link href={"/purchases/" + receipt.purchase_id} className="button primary" onClick={onNavigate}>View purchase<Icon name="arrow" size={17} /></Link> : <button className="button secondary" onClick={resource.refresh}><Icon name="refresh" size={16} />Refresh status</button>}</div></div>;
}
export function ReceiptUpload({ onNavigate }: { onNavigate?: () => void }) {
  const { api } = useSession();
  const input = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  useEffect(() => () => controller.current?.abort(), []);
  const choose = (files: FileList | null) => {
    if (!files?.length || busy) return;
    if (files.length !== 1) { setError("Add one receipt at a time."); return; }
    const problem = validateReceipt(files[0]);
    setError(problem ?? undefined); setFile(problem ? null : files[0]);
  };
  const upload = async () => {
    if (!file || busy) return;
    const active = new AbortController(); controller.current = active;
    setBusy(true); setError(undefined); setProgress(0);
    try { const result = await api.upload(file, setProgress, active.signal); if (!active.signal.aborted) setReceipt(result); }
    catch (cause) { if (!active.signal.aborted) setError(cause instanceof Error ? cause.message : "Upload failed. Please try again."); }
    finally { if (!active.signal.aborted) setBusy(false); }
  };
  if (receipt) return <ReceiptProgress initial={receipt} onNavigate={onNavigate} />;
  return <div className="upload-body"><CaptureSteps stage={busy ? 0 : -1} /><div className={"dropzone " + (dragging ? "dragging" : "")} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); choose(event.dataTransfer.files); }}><span className="empty-icon"><Icon name={file ? "file" : "upload"} size={28} /></span><h3>{file ? file.name : "Drop your receipt here"}</h3><p>{file ? "Ready to upload" : "or choose a file from your device"}</p><input ref={input} aria-label="Receipt file" type="file" accept=".jpg,.jpeg,.png,.pdf" onChange={event => choose(event.target.files)} disabled={busy} className="file-input" /><button className="button secondary" disabled={busy} onClick={() => input.current?.click()}>{file ? "Choose another file" : "Browse files"}</button><small>JPG, PNG or PDF · up to 10 MB</small></div>{busy && <div role="status"><div className="progress-label"><span>{progress === 100 ? "Saving your receipt…" : "Uploading…"}</span><span>{progress}%</span></div><progress max={100} value={progress} aria-label="Receipt upload progress" /></div>}{error && <ErrorState message={error} />}<div className="upload-footer"><p className="caption"><Icon name="shield" size={15} /> Only you can access your receipts.</p><button className="button primary" disabled={!file || busy} onClick={() => void upload()}>{busy ? "Uploading…" : "Upload receipt"}<Icon name="arrow" size={17} /></button></div></div>;
}

function CaptureSteps({ stage, failed = false }: { stage: number; failed?: boolean }) {
  return <ol className="capture-steps" aria-label="Receipt progress">{["Upload", "Process / extract", "Review", "Complete"].map((name, i) => {
    const position = i === 0 ? 0 : i + 1;
    const active = stage === position || (i === 1 && stage === 1);
    return <li key={name} className={(stage > position ? "step-done" : active ? "step-active" : "") + (failed && i === 1 ? " step-failed" : "")} aria-current={active ? "step" : undefined}><span>{stage > position ? <Icon name="check" size={15} /> : failed && i === 1 ? <Icon name="warning" size={15} /> : i + 1}</span><small>{name}</small></li>;
  })}</ol>;
}
