import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { Streamdown } from "streamdown";
import "streamdown/styles.css";
import styles from "./MarkdownBody.module.css";

export function MarkdownBody({
  text,
  streaming = false,
  compact = false,
}: {
  text: string;
  streaming?: boolean;
  /** Chat density: no outer block margins, so a one-line message is one line. */
  compact?: boolean;
}) {
  return (
    <div className={compact ? `${styles.md} ${styles.compact}` : styles.md}>
      <Streamdown
        mode={streaming ? "streaming" : "static"}
        plugins={{ code, cjk }}
        shikiTheme={["github-dark", "github-dark"]}
        controls={false}
        lineNumbers={false}
      >
        {text}
      </Streamdown>
    </div>
  );
}
