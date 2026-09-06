import { useEffect, useMemo, useRef, useState } from "react";
import { PydanticAIAgent } from "@ag-ui/pydantic-ai";
import type { AuthSession } from "../auth";
import { serviceRoot } from "../transport";
import type { Turn } from "../types";

interface AgentChatProps {
  auth: AuthSession;
  apiBase: string;
  workspaceId: string;
  branchId: string;
  sessionId: string;
  turns: Turn[];
  onSaved: () => Promise<void>;
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
        setStatus(`모델 실행에 실패했습니다. (${detail})`);
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
      setStatus("완료된 대화를 동기화했습니다.");
    } catch {
      setNeedsRefetch(true);
      setStatus(
        "대화는 완료됐지만 동기화에 실패했습니다. 동기화만 재시도하세요.",
      );
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
    setStatus("응답 생성 중…");
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
          : "요청 실패";
      setStatus(
        `응답 연결이 끊겼습니다. 입력과 부분 응답은 화면에 남아 있습니다. (${detail})`,
      );
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="agent-chat">
      <div aria-live="polite" className="chat-transcript">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <strong>SOT Agent</strong>
            <p>SOT의 가정과 대안을 함께 검토합니다.</p>
          </div>
        )}
        {messages.map((message) => {
          const content = textContent(message);
          const calls =
            "toolCalls" in message && Array.isArray(message.toolCalls)
              ? message.toolCalls
              : [];
          if (!content && calls.length === 0) return null;
          return (
            <article
              className={`chat-message ${message.role}`}
              key={message.id}
            >
              <strong>
                {message.role === "user"
                  ? "나"
                  : message.role === "assistant"
                    ? "SOT Agent"
                    : message.role === "tool"
                      ? "도구 결과"
                      : message.role}
              </strong>
              {content && <p>{content}</p>}
              {calls.map((call) => (
                <details className="tool-call" key={call.id} open>
                  <summary>도구 · {call.function.name}</summary>
                  {call.function.arguments && (
                    <pre>{call.function.arguments}</pre>
                  )}
                </details>
              ))}
            </article>
          );
        })}
      </div>
      <form className="chat-composer" onSubmit={(event) => void submit(event)}>
        <textarea
          aria-label="Agent message"
          disabled={running || needsRefetch}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="주장을 검토하거나 대안을 요청하세요"
          rows={3}
          value={input}
        />
        {running ? (
          <button
            className="button secondary"
            onClick={() => {
              stopped.current = true;
              agent.abortRun();
              setRunning(false);
              setStatus(
                "응답을 중지했습니다. 입력과 부분 응답은 화면에 남아 있습니다.",
              );
            }}
            type="button"
          >
            중지
          </button>
        ) : (
          <button
            className="button"
            disabled={needsRefetch || !input.trim()}
            type="submit"
          >
            보내기
          </button>
        )}
      </form>
      {needsRefetch && (
        <button
          className="button secondary save-retry"
          type="button"
          onClick={() => void refetch()}
        >
          동기화 재시도
        </button>
      )}
      <div aria-live="polite" className="sr-status">
        {status}
      </div>
    </div>
  );
}
