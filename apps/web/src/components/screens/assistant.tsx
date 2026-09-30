"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "../app-provider";
import { Icon } from "../icon";
import { ErrorState, Evidence, Loading, PageHeader, Pager } from "../ui";
import { useResource } from "@/lib/use-resource";
import { dateTime, label } from "@/lib/format";
import type { Message } from "@/lib/types";
function MessageBubble({ message }: { message: Message }) {
  const { profile } = useSession();
  return <article className={"message message-" + message.role.toLowerCase()}><span className="message-avatar"><Icon name={message.role === "ASSISTANT" ? "spark" : "receipt"} size={19} /></span><div className="message-body"><div className="message-label"><strong>{message.role === "ASSISTANT" ? "Raseed" : "You"}</strong><small>{dateTime(message.created_at, profile.locale, profile.timezone, true)}</small></div>{message.status === "PROCESSING" ? <p role="status" className="thinking">Looking through your purchase memory<span>…</span></p> : message.status === "FAILED" ? <ErrorState message={message.failure_message ?? "This response couldn't be completed. You can send your question again."} /> : <p className="message-content">{message.content}</p>}{message.evidence && message.evidence.citations.length > 0 && <details className="message-evidence"><summary><Icon name="shield" size={15} />{message.evidence.citations.length} evidence references</summary><dl>{message.evidence.citations.map((citation, index) => <div key={index}><dt>{label(citation.name)}</dt><dd>{citation.value == null ? "Unknown" : String(citation.value)}<small>{label(citation.tool_name)}</small></dd></div>)}</dl></details>}{message.tool_executions.length > 0 && <details className="message-evidence"><summary>Sources checked</summary>{message.tool_executions.map(tool => <details className="tool-result" key={tool.id}><summary>{label(tool.tool_name)} · {label(tool.status)}</summary>{tool.result?.error ? <p>{tool.result.error.message}</p> : <Evidence value={tool.result?.data} />}</details>)}</details>}</div></article>;
}
const starters = ["What did I spend this month?", "What should I use up soon?", "Show me my recent purchases.", "Can I get a product cheaper?"];
export function Assistant({ id }: { id?: string }) {
  const { api, demo } = useSession();
  const router = useRouter();
  const [historyOffset, setHistoryOffset] = useState(0);
  const [offset, setOffset] = useState(0);
  const history = useResource(signal => api.conversations({ limit: 20, offset: historyOffset }, signal), String(historyOffset));
  const messages = useResource(signal => id ? api.messages(id, { limit: 50, offset }, signal) : Promise.resolve([] as Message[]), (id ?? "new") + offset);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const pending = useRef<{ content: string; key: string; conversation: string } | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const processing = messages.data?.some(message => message.status === "PROCESSING") ?? false;
  const refreshMessages = messages.refresh;
  useEffect(() => {
    if (!processing) return;
    let count = 0;
    const timer = setInterval(() => { refreshMessages(); count++; if (count >= 40) clearInterval(timer); }, 3000);
    return () => clearInterval(timer);
  }, [processing, refreshMessages]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || busy || processing) return;
    setBusy(true); setError(undefined);
    let conversation = id;
    try {
      conversation = conversation ?? pending.current?.conversation ?? (await api.createConversation(content.slice(0, 100))).id;
      if (pending.current?.content !== content || pending.current.conversation !== conversation) pending.current = { content, key: crypto.randomUUID(), conversation };
      const turn = await api.sendMessage(conversation, content, pending.current.key);
      pending.current = null; setDraft("");
      setOffset(Math.floor((turn.assistant_message.sequence - 1) / 50) * 50);
      if (id !== conversation) router.replace("/assistant/" + conversation);
      else messages.refresh();
      history.refresh();
    } catch (cause) {
      setError((cause as Error).message);
      // Preserve this turn's key on an unknown outcome. Earlier failed turns
      // cannot establish whether this submission was accepted.
      if (conversation) {
        try {
          const rows = await api.messages(conversation, { limit: 100, offset });
          const request = rows.find(row => row.role === "USER" && row.idempotency_key === pending.current?.key);
          if (request && rows.some(row => row.reply_to_id === request.id && row.status === "FAILED")) pending.current = null;
        } catch { /* The outcome is still unknown; retry with the same key. */ }
        if (id === conversation) messages.refresh();
        history.refresh();
      }
    } finally { setBusy(false); }
  }
  return <><PageHeader eyebrow="YOUR PURCHASE MEMORY, IN CONVERSATION" title="A little help remembering." description="Ask about spending, find a purchase, or check what’s at home." /><div className="assistant-layout"><aside className="conversation-sidebar"><Link href="/assistant" className="button secondary full"><Icon name="plus" size={17} />New conversation</Link><p className="eyebrow">YOUR CONVERSATIONS</p>{history.loading ? <Loading compact /> : history.error ? <ErrorState message={history.error} retry={history.refresh} /> : history.data?.length ? <><nav aria-label="Conversations">{history.data.map(conversation => <Link href={"/assistant/" + conversation.id} key={conversation.id} aria-current={id === conversation.id ? "page" : undefined}><Icon name="assistant" size={17} /><span>{conversation.title ?? "Untitled conversation"}</span></Link>)}</nav><Pager offset={historyOffset} count={history.data.length} onChange={setHistoryOffset} /></> : <><p className="caption">{historyOffset ? "No conversations on this page." : "Your conversations will be kept here."}</p><Pager offset={historyOffset} count={0} onChange={setHistoryOffset} /></>}</aside><section className="chat"><div className="chat-transcript" aria-label="Conversation messages">{messages.loading ? <Loading /> : messages.error ? <ErrorState message={messages.error} retry={messages.refresh} /> : messages.data?.length ? <><div className="messages">{messages.data.map(message => <MessageBubble key={message.id} message={message} />)}</div><Pager offset={offset} count={messages.data.length} size={50} onChange={setOffset} /></> : offset > 0 ? <><p className="caption">No messages on this page.</p><Pager offset={offset} count={0} size={50} onChange={setOffset} /></> : <div className="chat-welcome"><span className="assistant-star"><Icon name="spark" size={34} /></span><h2>What’s on your mind?</h2><p>The details are in your receipts.<br />Let’s find the answer together.</p><div className="starter-grid">{starters.map(question => <button key={question} onClick={() => { setDraft(question); input.current?.focus(); }}>{question}<Icon name="arrow" size={16} /></button>)}</div></div>}{busy && <p className="chat-working" role="status"><Icon name="spark" size={16} />Raseed is checking your records…</p>}</div><div className="composer-area">{error && <ErrorState message={error} />}{processing && <button className="text-button" onClick={messages.refresh}>Refresh pending response<Icon name="refresh" size={15} /></button>}<form className="composer" onSubmit={event => void submit(event)}><textarea ref={input} value={draft} onChange={event => setDraft(event.target.value)} placeholder={demo ? "Browse a sample conversation from the list" : "Ask about your purchases…"} aria-label="Message Raseed" maxLength={8000} rows={2} disabled={busy || demo} /><button className="send-button" aria-label="Send message" disabled={!draft.trim() || busy || processing || demo}><Icon name="send" size={20} /></button></form><p className="caption">Answers use your recorded data. Check the evidence for important decisions.</p></div></section></div></>;
}
