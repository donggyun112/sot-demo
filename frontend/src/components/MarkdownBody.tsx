import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import remarkBreaks from "remark-breaks";
import remarkFrontmatter from "remark-frontmatter";
import remarkGfm from "remark-gfm";
import { Streamdown } from "streamdown";
import "streamdown/styles.css";
import type { Root, RootContent } from "mdast";
import styles from "./MarkdownBody.module.css";

/*
  Front matter is a block of YAML, and a reader of this product wants to see
  it: it is the top of a spec, not hidden metadata. Show it as the YAML it
  is, indentation and all. Left to plain Markdown its closing `---` is a
  setext underline, which turned two hundred lines of tokens into one
  enormous heading.
*/
function frontMatterAsCode() {
  return (tree: Root) => {
    const [first] = tree.children;
    if (first?.type !== "yaml") return;
    const block: RootContent = {
      type: "code",
      lang: "yaml",
      value: first.value,
    };
    tree.children[0] = block;
  };
}

/*
  GFM, because the agent answers with tables and task lists constantly and
  they were printing as rows of raw pipes. Declared here rather than assumed:
  nothing in the chain was adding it.

  remark-breaks, because a document here is whatever someone pasted or
  uploaded, not something an author wrote for a Markdown renderer. Plain
  Markdown joins consecutive lines into one paragraph, which turned an
  uploaded text file into a single unreadable run of text. Every newline in
  the source is a newline on screen.
*/
const plugins = [remarkGfm, remarkFrontmatter, frontMatterAsCode, remarkBreaks];

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
