import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import remarkBreaks from "remark-breaks";
import { Streamdown } from "streamdown";
import "streamdown/styles.css";
import styles from "./MarkdownBody.module.css";

/*
  A document here is whatever someone pasted or uploaded, not something an
  author wrote for a Markdown renderer. Plain Markdown joins consecutive
  lines into one paragraph, which turned an uploaded YAML file — a token
  spec, a config — into a single unreadable run of text. Every newline in
  the source is a newline on screen.
*/
const plugins = [remarkBreaks];

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
        remarkPlugins={plugins}
        shikiTheme={["github-dark", "github-dark"]}
        controls={false}
        lineNumbers={false}
      >
        {text}
      </Streamdown>
    </div>
  );
}
