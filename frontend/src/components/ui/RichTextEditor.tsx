import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Placeholder from "@tiptap/extension-placeholder";
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  List,
  ListOrdered,
  Heading1,
  Heading2,
  Heading3,
  Code,
  Quote,
  Undo,
  Redo,
  Minus,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useEffect } from "react";

interface RichTextEditorProps {
  content: string;
  onChange: (markdown: string) => void;
  className?: string;
  placeholder?: string;
}

function ToolbarButton({
  onClick,
  active,
  children,
  title,
}: {
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
  title: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        "rounded p-1.5 text-ink-muted hover:bg-bg-muted hover:text-ink transition-colors",
        active && "bg-bg-muted text-ink"
      )}
    >
      {children}
    </button>
  );
}

/** Convert TipTap HTML to a rough markdown string */
function htmlToMarkdown(html: string): string {
  let md = html;
  // Headings
  md = md.replace(/<h1[^>]*>(.*?)<\/h1>/gi, "# $1\n\n");
  md = md.replace(/<h2[^>]*>(.*?)<\/h2>/gi, "## $1\n\n");
  md = md.replace(/<h3[^>]*>(.*?)<\/h3>/gi, "### $1\n\n");
  // Bold / italic / underline / strike
  md = md.replace(/<strong>(.*?)<\/strong>/gi, "**$1**");
  md = md.replace(/<em>(.*?)<\/em>/gi, "*$1*");
  md = md.replace(/<u>(.*?)<\/u>/gi, "$1");
  md = md.replace(/<s>(.*?)<\/s>/gi, "~~$1~~");
  // Code
  md = md.replace(/<code>(.*?)<\/code>/gi, "`$1`");
  md = md.replace(/<pre><code[^>]*>([\s\S]*?)<\/code><\/pre>/gi, "```\n$1\n```\n\n");
  // Blockquote
  md = md.replace(/<blockquote>([\s\S]*?)<\/blockquote>/gi, (_, inner) => {
    return inner.replace(/<p>(.*?)<\/p>/gi, "> $1\n").trim() + "\n\n";
  });
  // Lists
  md = md.replace(/<ul>([\s\S]*?)<\/ul>/gi, (_, inner) => {
    return inner.replace(/<li><p>(.*?)<\/p><\/li>/gi, "- $1\n").replace(/<li>(.*?)<\/li>/gi, "- $1\n") + "\n";
  });
  md = md.replace(/<ol>([\s\S]*?)<\/ol>/gi, (_, inner) => {
    let i = 0;
    return inner.replace(/<li><p>(.*?)<\/p><\/li>/gi, () => `${++i}. $1\n`).replace(/<li>(.*?)<\/li>/gi, () => `${++i}. $1\n`) + "\n";
  });
  // Horizontal rule
  md = md.replace(/<hr\s*\/?>/gi, "---\n\n");
  // Paragraphs & line breaks
  md = md.replace(/<p>(.*?)<\/p>/gi, "$1\n\n");
  md = md.replace(/<br\s*\/?>/gi, "\n");
  // Strip remaining tags
  md = md.replace(/<[^>]+>/g, "");
  // Clean up extra newlines
  md = md.replace(/\n{3,}/g, "\n\n").trim();
  return md;
}

/** Convert markdown to basic HTML for TipTap initialization */
function markdownToHtml(md: string): string {
  let html = md;
  // Code blocks first
  html = html.replace(/```[\w]*\n([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
  // Headings
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  // Horizontal rule
  html = html.replace(/^---$/gm, "<hr>");
  // Bold / italic / strike / code
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/~~(.+?)~~/g, "<s>$1</s>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Blockquotes
  html = html.replace(/^> (.+)$/gm, "<blockquote><p>$1</p></blockquote>");
  // Unordered lists
  html = html.replace(/(?:^- .+\n?)+/gm, (match) => {
    const items = match.trim().split("\n").map((l) => `<li>${l.replace(/^- /, "")}</li>`).join("");
    return `<ul>${items}</ul>`;
  });
  // Ordered lists
  html = html.replace(/(?:^\d+\. .+\n?)+/gm, (match) => {
    const items = match.trim().split("\n").map((l) => `<li>${l.replace(/^\d+\. /, "")}</li>`).join("");
    return `<ol>${items}</ol>`;
  });
  // Paragraphs - wrap remaining plain text lines
  html = html.replace(/^(?!<[a-z])((?!<).+)$/gm, "<p>$1</p>");
  return html;
}

export default function RichTextEditor({ content, onChange, className, placeholder }: RichTextEditorProps) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Underline,
      Placeholder.configure({ placeholder: placeholder || "Start writing…" }),
    ],
    content: markdownToHtml(content),
    onUpdate: ({ editor }) => {
      onChange(htmlToMarkdown(editor.getHTML()));
    },
    editorProps: {
      attributes: {
        class: "prose-custom min-h-[350px] px-4 py-3 text-sm text-ink-soft focus:outline-none",
      },
    },
  });

  useEffect(() => {
    return () => {
      editor?.destroy();
    };
  }, [editor]);

  if (!editor) return null;

  const ic = "h-4 w-4";

  return (
    <div className={cn("rounded-lg border border-line bg-bg-surface overflow-hidden", className)}>
      <div className="flex flex-wrap items-center gap-0.5 border-b border-line bg-bg-muted/50 px-2 py-1.5">
        <ToolbarButton title="Bold" active={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}>
          <Bold className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Italic" active={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}>
          <Italic className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Underline" active={editor.isActive("underline")} onClick={() => editor.chain().focus().toggleUnderline().run()}>
          <UnderlineIcon className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Strikethrough" active={editor.isActive("strike")} onClick={() => editor.chain().focus().toggleStrike().run()}>
          <Strikethrough className={ic} />
        </ToolbarButton>
        <div className="mx-1 h-5 w-px bg-line" />
        <ToolbarButton title="Heading 1" active={editor.isActive("heading", { level: 1 })} onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}>
          <Heading1 className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Heading 2" active={editor.isActive("heading", { level: 2 })} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>
          <Heading2 className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Heading 3" active={editor.isActive("heading", { level: 3 })} onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}>
          <Heading3 className={ic} />
        </ToolbarButton>
        <div className="mx-1 h-5 w-px bg-line" />
        <ToolbarButton title="Bullet List" active={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}>
          <List className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Ordered List" active={editor.isActive("orderedList")} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
          <ListOrdered className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Blockquote" active={editor.isActive("blockquote")} onClick={() => editor.chain().focus().toggleBlockquote().run()}>
          <Quote className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Code" active={editor.isActive("code")} onClick={() => editor.chain().focus().toggleCode().run()}>
          <Code className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Horizontal Rule" onClick={() => editor.chain().focus().setHorizontalRule().run()}>
          <Minus className={ic} />
        </ToolbarButton>
        <div className="mx-1 h-5 w-px bg-line" />
        <ToolbarButton title="Undo" onClick={() => editor.chain().focus().undo().run()}>
          <Undo className={ic} />
        </ToolbarButton>
        <ToolbarButton title="Redo" onClick={() => editor.chain().focus().redo().run()}>
          <Redo className={ic} />
        </ToolbarButton>
      </div>
      <EditorContent editor={editor} />
    </div>
  );
}
