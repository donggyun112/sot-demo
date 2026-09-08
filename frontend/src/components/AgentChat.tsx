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
const canonicalMessages = (turns: Turn[]): AgentMessage[] =>
  turns.map(({ id, role, content }) => ({ id, role, content }));

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
  const [messages, setMessages] = useState<AgentMessage[]>(() => [
    ...agent.messages,
  ]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [needsRefetch, setNeedsRefetch] = useState(false);
  const [status, setStatus] = useState("");

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
    try {
      // The SDK's fetch boundary refreshes HTTP 401 before any stream is read.
      // RUN_ERROR, reader failures, and aborts are never replayed.
      await agent.runAgent();
      if (completed.current && !stopped.current) {
        setInput("");
        await refetch();
      }
    } catch (error) {
      const detail =
        error instanceof Error
          ? `${error.name}: ${error.message}`
          : t("agent.requestFailed");
      setStatus(t("agent.disconnected", { detail }));
    } finally {
      setRunning(false);
    }
  };

  const sendable = props.canSend !== false;
  const last = messages[messages.length - 1];
  return (
    <div className={styles.chat}>
      <div aria-live="polite" className={styles.transcript}>
        {/* One reading column shared by the transcript and the composer, so
            their left and right edges line up. */}
        <div className={turns.column}>
          {messages.map((message) => {
            const content = textContent(message);
            const calls =
              "toolCalls" in message && Array.isArray(message.toolCalls)
                ? message.toolCalls
                : [];
            if (!content && calls.length === 0) return null;
            const isUser = message.role === "user";
            // Tool work is process, not answer: it folds away under a step
            // count and reads at caption size, above the reply itself.
            const steps = message.role === "tool" ? 1 : calls.length;
            return (
              <TurnRow
                key={message.id}
                role={message.role}
                name={isUser ? props.youLabel : t("agent.name")}
              >
                {isUser ? (
                  <MarkdownBody compact text={content} />
                ) : (
                  <>
                    {steps > 0 && (
                      <details
                        className={styles.fold}
                        open={running && message === last}
                      >
                        <summary>{t("agent.steps", { count: steps })}</summary>
                        <div className={styles.foldBody}>
                          {message.role === "tool" ? (
                            <pre className={styles.toolOut}>{content}</pre>
                          ) : (
                            calls.map((call) => (
                              <details className={styles.step} key={call.id}>
                                <summary>
                                  <span className={styles.stepName}>
                                    {call.function.name}
                                  </span>
                                </summary>
                                {call.function.arguments && (
                                  <pre className={styles.toolOut}>
                                    {call.function.arguments}
                                  </pre>
                                )}
                              </details>
                            ))
                          )}
                        </div>
                      </details>
                    )}
                    {content && message.role !== "tool" && (
                      <div className={turns.prose}>
                        <MarkdownBody compact text={content} />
                      </div>
                    )}
                  </>
                )}
              </TurnRow>
            );
          })}
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

