// Guest feedback: stars, quick tags and comments guests leave after eating (/reports/feedback).
// Today shows the rating and the latest words (low ones first); Staff > Feedback shows everything.
import { motion } from "motion/react";
import { MessageSquareText, Star } from "lucide-react";
import { useState } from "react";
import { Avatar } from "../../ui/logo";
import { Badge, Card, Empty, Segmented, SectionTitle, Skeleton, ease } from "../../ui/kit";
import { Kpi, KpiStrip, clockOf } from "./bits";
import { useReport, type Ctx } from "./Owner";

export type FeedbackComment = { id: string; rating: number; tags: string[]; comment: string | null; table_ref: string | null; created_at: string; low: boolean; seen: boolean; seen_by: string | null };
export type FeedbackReport = {
  count: number;
  average: number | null;
  stars: Record<string, number>;
  tags: Record<string, number>;
  low: number;
  by_waiter: Record<string, { count: number; average: number }>;
  comments: FeedbackComment[];
};

const TAG: Record<string, string> = { food: "Food", service: "Service", speed: "Speed", value: "Value", clean: "Clean", slow: "Slow", cold: "Cold food", wrong_order: "Wrong order" };
const BAD_TAGS = new Set(["slow", "cold", "wrong_order"]);
export const tagName = (t: string) => TAG[t] ?? t.replace(/_/g, " ");
export const rating = (n: number | null | undefined) => (n === null || n === undefined ? "—" : n.toFixed(1));

/** The period's feedback; quiet, because an older server has no feedback report. */
export const useFeedback = (ctx: Ctx) => useReport<FeedbackReport>(ctx, "/reports/feedback", true, true);

/** "4.6 ★": a rating with one small star. */
export function RatingValue({ value, size = 18 }: { value: number | null | undefined; size?: number }) {
  return (
    <span className="inline-flex items-center gap-1">
      {rating(value)}
      {value !== null && value !== undefined ? <Star size={size} strokeWidth={0} className="fill-ink" /> : null}
    </span>
  );
}

const day = (iso: string) => {
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString() ? clockOf(iso) : `${d.toLocaleDateString([], { day: "numeric", month: "short" })} · ${clockOf(iso)}`;
};

/** One comment: the stars in a small square, the words, then table · time · tags. */
export function CommentRow({ c }: { c: FeedbackComment }) {
  return (
    <div className="feedback-row flex gap-3 border-t border-line py-3.5 first:border-0">
      <span className={`num grid h-11 w-11 shrink-0 place-items-center rounded-xl text-[15px] font-bold ${c.low ? "bg-bad-soft text-bad" : "bg-canvas text-ink"}`}>
        <span className="inline-flex items-center gap-0.5">
          {c.rating}
          <Star size={11} strokeWidth={0} className={c.low ? "fill-bad" : "fill-ink"} />
        </span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] leading-snug">{c.comment}</span>
        <span className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[13px] text-muted">
          <span className="font-medium text-ink/80">{c.table_ref ? `Table ${c.table_ref.toUpperCase()}` : "Kiosk"}</span>
          <span>· {day(c.created_at)}</span>
          {c.tags.length ? <span>· {c.tags.map(tagName).join(", ")}</span> : null}
          {c.low ? <span>· {c.seen ? `seen${c.seen_by ? ` by ${c.seen_by}` : ""}` : <span className="font-semibold text-bad">not seen yet</span>}</span> : null}
        </span>
      </span>
    </div>
  );
}

/** Low ratings first, then the newest. */
const lowFirst = (l: FeedbackComment[]) => [...l].sort((a, b) => Number(b.low) - Number(a.low) || b.created_at.localeCompare(a.created_at));

/** For Today: the rating and what guests said lately. */
export function GuestVoice({ f, onAll }: { f: FeedbackReport | null; onAll: () => void }) {
  if (!f) return null;
  const latest = lowFirst(f.comments).slice(0, 4);
  return (
    <Card>
      <SectionTitle
        title="What guests say"
        hint={f.count ? `${f.count} ${f.count === 1 ? "rating" : "ratings"} · ${f.low} low` : undefined}
        right={
          <button onClick={onAll} className="text-sm font-semibold text-accent hover:underline">
            See all
          </button>
        }
      />
      {latest.length ? latest.map((c) => <CommentRow key={c.id} c={c} />) : <Empty icon={<MessageSquareText size={22} />}>No comments from guests in this period.</Empty>}
    </Card>
  );
}

/** Staff > Feedback: the whole picture for the period. */
export function FeedbackView({ f, failed }: { f: FeedbackReport | null; failed: boolean }) {
  const [which, setWhich] = useState<"all" | "low">("all");
  if (!f)
    return failed ? (
      <Card>
        <Empty icon={<MessageSquareText size={22} />}>Guest feedback is not available on this server yet.</Empty>
      </Card>
    ) : (
      <>
        <Skeleton className="h-[100px] rounded-2xl" />
        <Skeleton className="h-64 rounded-2xl" />
      </>
    );
  const max = Math.max(1, ...Object.values(f.stars));
  const tags = Object.entries(f.tags).sort((a, b) => b[1] - a[1]);
  const tagMax = Math.max(1, ...tags.map((t) => t[1]));
  const waiters = Object.entries(f.by_waiter).sort((a, b) => b[1].average - a[1].average);
  const shown = (which === "low" ? f.comments.filter((c) => c.low) : f.comments).slice().sort((a, b) => b.created_at.localeCompare(a.created_at));
  const unseen = f.comments.filter((c) => c.low && !c.seen).length;
  return (
    <>
      <KpiStrip>
        <Kpi label="Guests' rating" value={<RatingValue value={f.average} size={20} />} hint="average stars" />
        <Kpi label="Ratings" value={f.count} hint={`${f.comments.length} with a comment`} />
        <Kpi label="Low ratings" value={f.low} hint="2 stars or fewer" tone={f.low ? "bad" : undefined} />
        <Kpi label="Low, not seen" value={unseen} hint={unseen ? "no one went to the table yet" : "all followed up"} tone={unseen ? "warn" : undefined} />
      </KpiStrip>

      <div className={`grid items-start gap-4 lg:grid-cols-2 ${waiters.length ? "xl:grid-cols-3" : ""}`}>
        <Card>
          <SectionTitle title="Stars" hint={f.count ? `${f.count} ratings` : undefined} />
          <div className="flex flex-col gap-2.5">
            {[5, 4, 3, 2, 1].map((n, i) => {
              const v = f.stars[String(n)] ?? 0;
              return (
                <div key={n} className="star-row grid grid-cols-[2.5rem_1fr_2.5rem] items-center gap-3 text-sm">
                  <span className="inline-flex items-center gap-1 font-semibold">
                    {n} <Star size={12} strokeWidth={0} className="fill-ink" />
                  </span>
                  <span className="h-2 overflow-hidden rounded-full bg-ink/[.06]">
                    <motion.span className={`block h-full rounded-full ${n <= 2 ? "bg-bad" : "bg-accent"}`} initial={{ width: 0 }} animate={{ width: `${v ? Math.max(2, (100 * v) / max) : 0}%` }} transition={{ ...ease, duration: 0.6, delay: i * 0.04 }} />
                  </span>
                  <span className="num text-right text-muted">{v}</span>
                </div>
              );
            })}
          </div>
        </Card>
        <Card>
          <SectionTitle title="What they mention" />
          {tags.length ? (
            <div className="flex flex-col">
              {tags.map(([t, n]) => (
                <div key={t} className="flex items-center gap-3 border-t border-line py-2.5 first:border-0 first:pt-0">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${BAD_TAGS.has(t) ? "bg-bad" : "bg-ok"}`} />
                  <span className="min-w-0 flex-1 truncate text-[15px] font-medium">{tagName(t)}</span>
                  <span className="hidden h-1.5 w-28 overflow-hidden rounded-full bg-ink/[.06] sm:block">
                    <span className="block h-full rounded-full bg-accent" style={{ width: `${(100 * n) / tagMax}%` }} />
                  </span>
                  <span className="num w-8 text-right font-semibold">{n}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-6 text-center text-muted">No tags yet</p>
          )}
        </Card>
        {waiters.length ? (
          <Card className="lg:col-span-2 xl:col-span-1">
            <SectionTitle title="By waiter" hint="Who took the food to the table" />
            {waiters.map(([name, w]) => (
              <div key={name} className="flex items-center gap-3 border-t border-line py-2.5 first:border-0 first:pt-0">
                <Avatar size={36} />
                <span className="min-w-0 flex-1 truncate text-[15px] font-semibold">{name}</span>
                <span className="text-sm text-muted">
                  {w.count} {w.count === 1 ? "rating" : "ratings"}
                </span>
                <span className="num w-16 text-right font-bold">
                  <RatingValue value={w.average} size={14} />
                </span>
              </div>
            ))}
          </Card>
        ) : null}
      </div>

      <Card>
        <SectionTitle
          title="Every comment"
          hint={`${shown.length} ${shown.length === 1 ? "comment" : "comments"}`}
          right={
            <Segmented
              className="[&>button]:h-9 [&>button]:text-sm"
              value={which}
              onChange={setWhich}
              options={[
                ["all", "All"],
                ["low", <>Low {f.low ? <Badge tone="bad">{f.comments.filter((c) => c.low).length}</Badge> : null}</>],
              ]}
            />
          }
        />
        {shown.length ? shown.map((c) => <CommentRow key={c.id} c={c} />) : <Empty icon={<MessageSquareText size={22} />}>{which === "low" ? "No low ratings with a comment." : "No comments in this period."}</Empty>}
      </Card>
    </>
  );
}
