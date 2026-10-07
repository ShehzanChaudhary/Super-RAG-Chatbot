import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Bot, Check, Copy, FileText } from "lucide-react";
import type { Citation } from "../api/client";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[] | null;
  streaming?: boolean;
  verified?: boolean;
}

/**
 * Charts: the backend can put a fenced block in the answer:
 * ```chart
 * {"type":"bar","title":"Total funds","xKey":"year",
 *  "series":[{"key":"total","name":"Total (₹ crore)"}],
 *  "data":[{"year":"FY2022","total":757472},{"year":"FY2023","total":801652}]}
 * ```
 * type can be "bar" or "line".
 */
interface ChartSpec {
  type: "bar" | "line";
  title?: string;
  xKey: string;
  series: { key: string; name?: string }[];
  data: Record<string, string | number>[];
}

const CHART_COLORS = ["#173a66", "#9e2a2b", "#2d8cf0", "#d99a2b", "#3f9b6b"];

function ChartBlock({ raw, streaming }: { raw: string; streaming: boolean }) {
  let spec: ChartSpec | null = null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && Array.isArray(parsed.data) && Array.isArray(parsed.series) && parsed.xKey) {
      spec = parsed as ChartSpec;
    }
  } catch {
    // incomplete JSON while streaming, or a bad block
  }

  if (!spec) {
    return (
      <p className="my-3 rounded-lg bg-brand-sky px-3 py-2 text-sm text-gray-500">
        {streaming ? "Preparing chart..." : "The chart could not be displayed."}
      </p>
    );
  }

  const Chart = spec.type === "line" ? LineChart : BarChart;

  return (
    <figure className="my-4 rounded-xl border border-gray-200 bg-white p-3">
      {spec.title && (
        <figcaption className="mb-2 px-1 text-sm font-semibold text-brand-navy">
          {spec.title}
        </figcaption>
      )}
      <div className="h-72 w-full">
        <ResponsiveContainer>
          <Chart data={spec.data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey={spec.xKey} tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} width={64} />
            <Tooltip />
            {spec.series.length > 1 && <Legend />}
            {spec.series.map((s, i) =>
              spec.type === "line" ? (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name ?? s.key}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                />
              ) : (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  name={s.name ?? s.key}
                  fill={CHART_COLORS[i % CHART_COLORS.length]}
                  radius={[4, 4, 0, 0]}
                />
              ),
            )}
          </Chart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard blocked, nothing to do
    }
  }

  return (
    <button
      onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-brand-navy transition hover:border-brand-navy"
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function Avatar() {
  return (
    <div
      className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-maroon text-white"
      aria-hidden
    >
      <Bot size={17} />
    </div>
  );
}

function textOf(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(textOf).join("");
  return "";
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
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand-navy px-4 py-2.5 text-white">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3">
      <Avatar />
      <div className="min-w-0 max-w-[92%] flex-1">
        <div className="rounded-2xl rounded-tl-md bg-white px-5 py-4 shadow-sm ring-1 ring-black/5">
          {content === "" && streaming ? (
            <div className="flex items-center gap-1.5 py-1" aria-label="Searching the reports">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-2 w-2 animate-bounce rounded-full bg-brand-navy/40"
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              ))}
            </div>
          ) : (
            <div className="leading-relaxed text-gray-800">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div className="my-3 overflow-x-auto rounded-lg border border-gray-200">
                      <table className="min-w-full border-collapse text-sm">{children}</table>
                    </div>
                  ),
                  th: ({ children }) => (
                    <th className="border-b border-gray-200 bg-brand-sky px-3 py-2 text-left font-semibold text-brand-navy">
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="border-b border-gray-100 px-3 py-2">{children}</td>
                  ),
                  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
                  ul: ({ children }) => <ul className="my-2 list-disc pl-6">{children}</ul>,
                  ol: ({ children }) => <ol className="my-2 list-decimal pl-6">{children}</ol>,
                  h1: ({ children }) => (
                    <h3 className="mb-2 mt-4 text-lg font-bold text-brand-navy">{children}</h3>
                  ),
                  h2: ({ children }) => (
                    <h3 className="mb-2 mt-4 text-lg font-bold text-brand-navy">{children}</h3>
                  ),
                  h3: ({ children }) => (
                    <h4 className="mb-1 mt-3 font-semibold text-brand-navy">{children}</h4>
                  ),
                  pre: ({ children }) => <>{children}</>,
                  code: ({ className, children }) => {
                    const raw = textOf(children).replace(/\n$/, "");
                    if (className === "language-chart") {
                      return <ChartBlock raw={raw} streaming={streaming} />;
                    }
                    if (className?.startsWith("language-")) {
                      return (
                        <pre className="my-3 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs text-gray-100">
                          <code>{raw}</code>
                        </pre>
                      );
                    }
                    return (
                      <code className="rounded bg-gray-100 px-1 py-0.5 text-[0.9em]">
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          )}

          {!streaming && !verified && (
            <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
              The sources of this answer could not be verified. Please check the numbers in the
              report.
            </p>
          )}

          {!streaming && citations && citations.length > 0 && (
            <div className="mt-4 border-t border-gray-100 pt-3">
              <p className="mb-2 text-xs font-semibold text-gray-500">Sources</p>
              <div className="flex flex-wrap gap-2">
                {citations.map((c) => (
                  <a
                    key={`${c.doc_name}-${c.pdf_page}`}
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={`Open ${c.doc_name}, page ${c.pdf_page}`}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-brand-blue/40 bg-brand-sky px-2.5 py-1 text-xs text-brand-navy transition hover:border-brand-maroon hover:text-brand-maroon"
                  >
                    <FileText size={13} aria-hidden />
                    {c.report_year} · page {c.pdf_page}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>

        {!streaming && content && (
          <div className="mt-2 flex gap-2">
            <CopyButton text={content} />
          </div>
        )}
      </div>
    </div>
  );
}