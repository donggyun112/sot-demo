import type { ReactNode } from "react";
import { MarkdownBody } from "./MarkdownBody";
import styles from "./Turn.module.css";

/**
 * One turn in a conversation, wherever that conversation is read: a live agent
 * session or a shared one. You speak from the right in a bubble; the reply is
 * the thing being read, so it takes the full column on the left. The speaker
 * line sits with its own text rather than on the opposite edge.
 */
export function Turn({
  role,
  name,
  children,
}: {
  role: string;
  name: string;
  children: ReactNode;
}) {
  return (
    <article className={styles.turn} data-role={role}>
      <div className={styles.who}>
        <span aria-hidden="true" className={styles.av} data-role={role}>
          {name.slice(0, 1)}
        </span>
        <span className={styles.name}>{name}</span>
      </div>
      {role === "user" ? (
        <div className={styles.userBubble}>{children}</div>
      ) : (
        children
      )}
    </article>
  );
}

/** A read-only transcript: no composer, no tool folds, no streaming. */
export function Transcript({
  turns,
  youLabel,
  agentLabel,
}: {
  turns: readonly { role: string; content: string }[];
  youLabel: string;
  agentLabel: string;
}) {
  return (
    <div className={styles.column}>
      {turns.map((turn, index) => (
        <Turn
          key={index}
          role={turn.role}
          name={turn.role === "user" ? youLabel : agentLabel}
        >
          <div className={styles.prose}>
            <MarkdownBody compact text={turn.content} />
          </div>
        </Turn>
      ))}
    </div>
  );
}
