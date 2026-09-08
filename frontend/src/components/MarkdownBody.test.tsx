import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { MarkdownBody } from "./MarkdownBody";

const TABLE = ["| 위치 | 노출 |", "|---|---|", "| a.tsx:1 | UUID |"].join("\n");

it("renders a table the agent wrote as a table", () => {
  // The agent answers with tables constantly. Printed as raw pipes they are
  // unreadable, and the document body has the same renderer.
  render(<MarkdownBody text={TABLE} />);

  expect(screen.getByRole("table")).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "위치" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "UUID" })).toBeVisible();
});

it("keeps the line structure of text nobody wrote for a renderer", () => {
  // An uploaded YAML file is lines, not a paragraph.
  const { container } = render(<MarkdownBody text={"xs: 4px\nsm: 8px"} />);

  expect(container.querySelectorAll("br")).toHaveLength(1);
});

it("shows front matter as the YAML it is", () => {
  // Its closing --- is a setext underline in plain Markdown, which turned two
  // hundred lines of tokens into one enormous heading.
  const { container } = render(
    <MarkdownBody text={"---\nname: SOT\n---\n\n## Overview\n\n본문."} />,
  );

  expect(container.querySelector("pre")).not.toBeNull();
  expect(screen.getByRole("heading", { name: "Overview" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: /name: SOT/ })).toBeNull();
});
