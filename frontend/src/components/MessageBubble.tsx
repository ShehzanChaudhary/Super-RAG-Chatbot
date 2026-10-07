import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "../api/client";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[] | null;
  streaming?: boolean;
  verified?: boolean;
}

export default function MessageBubble({
  role,
  content,
  citations,
  streaming = false,
  verified = true,
}: MessageBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-brand-navy px-4 py-2 text-white">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] rounded-lg bg-white px-4 py-3 shadow-sm">
        {content === "" && streaming ? (
          <p className="text-sm text-gray-400">Searching the reports...</p>
        ) : (
          <div className="prose-answer">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ children }) => (
                  <div className="my-3 overflow-x-auto">
                    <table className="min-w-full border-collapse text-sm">
                      {children}
                    </table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-gray-300 bg-brand-sky px-3 py-1.5 text-left font-semibold text-brand-navy">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="border border-gray-300 px-3 py-1.5">{children}</td>
                ),
                p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="my-2 list-disc pl-6">{children}</ul>,
                ol: ({ children }) => <ol className="my-2 list-decimal pl-6">{children}</ol>,
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        )}

        {!streaming && !verified && (
          <p className="mt-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
            The sources of this answer could not be verified. Please check the
            numbers in the report.
          </p>
        )}

        {!streaming && citations && citations.length > 0 && (
          <div className="mt-3 border-t border-gray-200 pt-2">
            <p className="mb-1 text-xs font-semibold uppercase text-gray-500">Sources</p>
            <div className="flex flex-wrap gap-2">
              {citations.map((c) => (
                <a
                  key={`${c.doc_name}-${c.pdf_page}`}
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded border border-brand-blue/40 bg-brand-sky px-2 py-1 text-xs text-brand-navy transition hover:border-brand-maroon hover:text-brand-maroon"
                >
                  {c.report_year} · page {c.pdf_page}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}