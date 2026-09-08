import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PydanticAIAgent } from "@ag-ui/pydantic-ai";
import type { AuthSession } from "../auth";
import { serviceRoot } from "../transport";
import type { Turn } from "../types";
import { MarkdownBody } from "./MarkdownBody";
import { Turn as TurnRow } from "./Turn";
import turns from "./Turn.module.css";
import styles from "./AgentChat.module.css";

interface AgentChatProps {
  auth: AuthSession;
  apiBase: string;
  workspaceId: string;
  branchId: string;
  sessionId: string;
  turns: Turn[];
  onSaved: () => Promise<void>;
  canSend?: boolean;
  youLabel: string;
}
type AgentMessage = PydanticAIAgent["messages"][number];
/**
 * What the model is replayed: the conversation itself. A stored tool turn is
 * the NAME of what the agent did, not the call the model would need to resume
 * from, so it belongs in the record below rather than in this history.
 */
const canonicalMessages = (turns: Turn[]): AgentMessage[] =>
  turns
    .filter((turn) => turn.role === "user" || turn.role === "assistant")
    .map(({ id, role, content }) => ({
      id,
      role: role as "user" | "assistant",
      content,
    }));

function textContent(message: AgentMessage): string {
  const content = "content" in message ? message.content : "";
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object" && "text" in part)
        return String(part.text);
      return "";
    })
    .join("");
}

type ToolEnvelope = {
  kind?: string;
  tool_name?: string;
  tool_call_id?: string;
  args?: unknown;
  result?: unknown;
};

/** The envelope the server wraps a tool turn in, or null for anything else. */
function toolEnvelope(text: string): ToolEnvelope | null {
  if (!text.startsWith("{")) return null;
  try {
    const value: unknown = JSON.parse(text);
    return value && typeof value === "object" ? (value as ToolEnvelope) : null;
  } catch {
    return null;
  }
}

/**
 * One entry in the transcript, in the order it happened.
 *
 * A tool call sits between the turns it sits between: hoisting every call to
 * the end lost the one thing the record is for, which is knowing what the
 * agent did and when.
 */
type Block =
  | { kind: "text"; id: string; role: string; content: string }
  | { kind: "tool"; id: string; name: string; args?: unknown; result?: unknown };

/** A call and its result are one thing that happened, so they read as one. */
function attachResult(blocks: Block[], callId: string, result: unknown) {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const block = blocks[i];
    if (block.kind === "tool" && block.id === callId) {
      block.result = result;
      return true;
    }
  }
  return false;
}

/** The live run: AG-UI messages, already in order. */
function liveBlocks(messages: readonly AgentMessage[]): Block[] {
  const blocks: Block[] = [];
  for (const message of messages) {
    if ("toolCalls" in message && Array.isArray(message.toolCalls))
      for (const call of message.toolCalls)
        blocks.push({
          kind: "tool",
          id: call.id,
          name: call.function.name,
          args: call.function.arguments
            ? (toolEnvelope(call.function.arguments)?.args ??
              call.function.arguments)
            : undefined,
        });
    if (message.role === "tool") {
      const envelope = toolEnvelope(textContent(message));
      if (!envelope?.tool_call_id) continue;
      if (envelope.kind === "call")
        blocks.push({
          kind: "tool",
          id: envelope.tool_call_id,
          name: envelope.tool_name ?? "",
          args: envelope.args,
        });
      else if (!attachResult(blocks, envelope.tool_call_id, envelope.result))
        blocks.push({
          kind: "tool",
          id: envelope.tool_call_id,
          name: envelope.tool_name ?? "",
          result: envelope.result,
        });
      continue;
    }
    const content = textContent(message);
    if (content)
      blocks.push({
        kind: "text",
        id: message.id,
        role: message.role,
        content,
      });
  }
  return blocks;
}

/** What was stored: turns in their own order, tool calls named. */
function storedBlocks(turns: Turn[]): Block[] {
  return turns.map((turn) =>
    turn.role === "tool"
      ? { kind: "tool" as const, id: turn.id, name: turn.content }
      : {
          kind: "text" as const,
          id: turn.id,
          role: turn.role,
          content: turn.content,
        },
  );
}

export function AgentChat(props: AgentChatProps) {
  const { t } = useTranslation();
  const agent = useMemo(
    () =>
      new PydanticAIAgent({
        url: `${serviceRoot(props.apiBase)}/api/v1/workspaces/${encodeURIComponent(props.workspaceId)}/branches/${encodeURIComponent(props.branchId)}/agent`,
        threadId: props.sessionId,
        fetch: (url, init) => props.auth.fetch(new Request(url, init)),
        initialMessages: canonicalMessages(props.turns),
      }),
    [
      props.auth,
      props.apiBase,
      props.workspaceId,
      props.branchId,
      props.sessionId,
    ],
  );
  const latest = useRef(props);
  latest.current = props;
  const completed = useRef(false);
  const stopped = useRef(false);
  const preservePartial = useRef(false);
  /* The draft that is in flight, so stopping or failing gives it back. */
  const sent = useRef("");
  const [messages, setMessages] = useState<AgentMessage[]>(() => [
    ...agent.messages,
  ]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [needsRefetch, setNeedsRefetch] = useState(false);
  const [status, setStatus] = useState("");
  /* Which tool records the reader has opened, so a re-render leaves them. */
  const [folds, setFolds] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const subscription = agent.subscribe({
      onMessagesChanged: ({ messages: next }) => setMessages([...next]),
      onRunFinishedEvent: () => {
        completed.current = true;
      },
      onRunErrorEvent: ({ event }) => {
        preservePartial.current = true;
        const detail = event.code
          ? `${event.code}: ${event.message}`
          : event.message;
        setStatus(t("agent.runFailed", { detail }));
      },
    });
    return () => {
      stopped.current = true;
      subscription.unsubscribe();
      if (agent.isRunning) agent.abortRun();
    };
  }, [agent]);

  useEffect(() => {
    if (!running && !preservePartial.current && !needsRefetch) {
      agent.setMessages(canonicalMessages(props.turns));
      setMessages([...agent.messages]);
    }
  }, [agent, props.turns, running, needsRefetch]);

  const refetch = async () => {
    try {
      await latest.current.onSaved();
      preservePartial.current = false;
      setNeedsRefetch(false);
      setStatus(t("agent.synced"));
    } catch {
      setNeedsRefetch(true);
      setStatus(t("agent.syncFailed"));
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const content = input.trim();
    if (!content || running || needsRefetch || agent.isRunning) return;
    stopped.current = false;
    completed.current = false;
    preservePartial.current = true;
    setRunning(true);
    setStatus(t("agent.running"));
    // A failed draft stays visible, but the next run starts from server-owned Turns.
    agent.setMessages(canonicalMessages(latest.current.turns));
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content });
    // The message is in the transcript now, so the box is empty: leaving the
    // draft sitting there made it look like nothing had been sent.
    sent.current = content;
    setInput("");
    try {
      // The SDK's fetch boundary refreshes HTTP 401 before any stream is read.
      // RUN_ERROR, reader failures, and aborts are never replayed.
      await agent.runAgent();
      if (completed.current && !stopped.current) await refetch();
    } catch (error) {
      const detail =
        error instanceof Error
          ? `${error.name}: ${error.message}`
          : t("agent.requestFailed");
      setStatus(t("agent.disconnected", { detail }));
    } finally {
      setRunning(false);
      // A run that did not finish gives the draft back rather than losing it.
      if (!completed.current || stopped.current) setInput(content);
    }
  };

  const sendable = props.canSend !== false;
  // While a run streams — or after one that failed or was stopped, whose
  // partial output is still on screen — the live messages are the record.
  // Once it lands and syncs, the stored turns are. Both are already in order.
  const settled = !running && !preservePartial.current && !needsRefetch;
  const blocks = settled ? storedBlocks(props.turns) : liveBlocks(messages);

  return (
    <div className={styles.chat}>
      <div aria-live="polite" className={styles.transcript}>
        {/* One reading column shared by the transcript and the composer, so
            their left and right edges line up. */}
        <div className={turns.column}>
          {blocks.map((block) =>
            block.kind === "text" ? (
              <TurnRow
                key={block.id}
                role={block.role}
                name={block.role === "user" ? props.youLabel : t("agent.name")}
              >
                {block.role === "user" ? (
                  <MarkdownBody compact text={block.content} />
                ) : (
                  <div className={turns.prose}>
                    <MarkdownBody compact text={block.content} />
                  </div>
                )}
              </TurnRow>
            ) : (
              <details
                className={styles.fold}
                key={block.id}
                /* Uncontrolled once touched: writing `open` on every render
                   fought the click that opened it. */
                open={folds[block.id] ?? running}
                onToggle={(event) =>
                  setFolds((current) => ({
                    ...current,
                    [block.id]: event.currentTarget.open,
                  }))
                }
              >
                <summary>
                  <span className={styles.stepName}>{block.name}</span>
                </summary>
                <div className={styles.foldBody}>
                  {block.args !== undefined && (
                    <pre className={styles.toolOut}>
                      {JSON.stringify(block.args, null, 2)}
                    </pre>
                  )}
                  {block.result !== undefined && (
                    <pre className={styles.toolOut}>
                      {JSON.stringify(block.result, null, 2)}
                    </pre>
                  )}
                </div>
              </details>
            ),
          )}
        </div>
      </div>
      {sendable && (
        <form className={styles.composer} onSubmit={(event) => void submit(event)}>
          <div className={styles.card}>
            <label className={styles.field}>
              <textarea
                aria-label={t("agent.message")}
                disabled={running || needsRefetch}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  // Enter sends, Shift+Enter breaks the line.
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submit(event);
                  }
                }}
                placeholder={t("agent.placeholder")}
                rows={1}
                value={input}
              />
            </label>
            <div className={styles.actions}>
              {needsRefetch && (
                <button
                  className={styles.retry}
                  type="button"
                  onClick={() => void refetch()}
                >
                  {t("agent.retry")}
                </button>
              )}
              {running ? (
                <button
                  data-kind="stop"
                  onClick={() => {
                    stopped.current = true;
                    agent.abortRun();
                    setRunning(false);
                    setInput(sent.current);
                    setStatus(t("agent.stopped"));
                  }}
                  type="button"
                >
                  {t("agent.stop")}
                </button>
              ) : (
                <button disabled={needsRefetch || !input.trim()} type="submit">
                  {t("agent.send")}
                </button>
              )}
            </div>
          </div>
        </form>
      )}
      <div aria-live="polite" className={styles.status}>
        {status}
      </div>
    </div>
  );
}

