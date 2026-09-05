import { useEffect, useMemo, useRef, useState } from "react";
import { PydanticAIAgent } from "@ag-ui/pydantic-ai";
import {
  CopilotChat,
  CopilotKitProvider,
  UseAgentUpdate,
  useAgent,
  type Message,
} from "@copilotkitnext/react";

import type { SOTApi } from "../api";
import type { ActorId, NewTurn, Turn } from "../types";

interface AgentChatProps {
  actor: ActorId;
  api: SOTApi;
  apiBase: string;
  branchId: string;
  sessionId: string;
  turns: Turn[];
  onSaved: () => void;
}

function textContent(message: Message): string {
  const content = "content" in message ? message.content : "";
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object" && "text" in part) {
        return String(part.text);
      }
      return "";
    })
    .join("");
}

function TranscriptCommitter({
  api,
  branchId,
  savedAssistantIds,
  onSaved,
}: Pick<AgentChatProps, "api" | "branchId" | "onSaved"> & {
  savedAssistantIds: Set<string>;
}) {
  const { agent } = useAgent({ updates: [UseAgentUpdate.OnRunStatusChanged] });
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState<NewTurn[] | null>(null);

  const persist = async (turns: NewTurn[], assistantId: string) => {
    try {
      await api.appendTurns(branchId, turns);
      savedAssistantIds.add(assistantId);
      setPending(null);
      setStatus("완료된 대화를 저장했습니다.");
      onSaved();
    } catch {
      setPending(turns);
      setStatus("대화 저장에 실패했습니다. 모델을 다시 실행하지 않고 저장만 재시도하세요.");
    }
  };

  useEffect(() => {
    const subscription = agent.subscribe({
      onRunFinalized: async ({ messages }) => {
        const assistantIndex = messages.findLastIndex(
          (message) => message.role === "assistant" && textContent(message).trim(),
        );
        if (assistantIndex < 0) return;
        const assistant = messages[assistantIndex];
        if (savedAssistantIds.has(assistant.id)) return;
        const user = messages
          .slice(0, assistantIndex)
          .findLast((message) => message.role === "user" && textContent(message).trim());
        if (!user) return;
        await persist(
          [
            { role: "user", content: textContent(user) },
            { role: "assistant", content: textContent(assistant) },
          ],
          assistant.id,
        );
      },
      onRunFailed: () => {
        setStatus("응답 연결이 끊겼습니다. 입력과 부분 응답은 화면에 남아 있습니다.");
      },
    });
    return subscription.unsubscribe;
  }, [agent, api, branchId, onSaved, savedAssistantIds]);

  return (
    <>
      <div aria-live="polite" className="sr-status">
        {status}
      </div>
      {pending && (
        <button
          className="button secondary"
          type="button"
          onClick={() => void persist(pending, `retry-${pending[1]?.content ?? "assistant"}`)}
        >
          저장 재시도
        </button>
      )}
    </>
  );
}

export function AgentChat(props: AgentChatProps) {
  const initialMessages = useMemo<Message[]>(
    () =>
      props.turns.map((turn) => ({
        id: turn.id,
        role: turn.role,
        content: turn.content,
      })) as Message[],
    [props.turns],
  );
  const savedAssistantIds = useRef(
    new Set(props.turns.filter((turn) => turn.role === "assistant").map((turn) => turn.id)),
  ).current;
  const agent = useMemo(
    () =>
      new PydanticAIAgent({
        url: `${props.apiBase}/branches/${props.branchId}/agent`,
        headers: { "X-SOT-User": props.actor },
        threadId: props.sessionId,
        initialMessages,
      }),
    [props.actor, props.apiBase, props.branchId, props.sessionId, initialMessages],
  );

  return (
    <CopilotKitProvider agents__unsafe_dev_only={{ default: agent }}>
      <TranscriptCommitter
        api={props.api}
        branchId={props.branchId}
        savedAssistantIds={savedAssistantIds}
        onSaved={props.onSaved}
      />
      <CopilotChat
        agentId="default"
        threadId={props.sessionId}
        labels={{
          chatInputPlaceholder: "주장을 검토하거나 대안을 요청하세요",
          welcomeMessageText: "SOT의 가정과 대안을 함께 검토합니다.",
        }}
      />
    </CopilotKitProvider>
  );
}
