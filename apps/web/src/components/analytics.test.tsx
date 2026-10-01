import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { SessionContext } from "./app-provider";
import { CategoryComparison } from "./spending-breakdowns";
import { Change, TrendChart } from "./charts";
import { Analysis } from "./screens/analysis";
import { session } from "@/test/fixtures";
import type { CategoryGroup } from "@/lib/types";

const period = { start_date: "2026-09-01", end_date: "2026-10-01", timezone: "Asia/Kolkata" };
const previous = { ...period, start_date: "2026-08-01", end_date: "2026-09-01" };
const category: CategoryGroup = { category_id: "food", category_name: "Groceries", currency: "INR", total_amount: "1234.560001", share_of_known_total_percent: "100", purchase_count: 1 };
const show = (children: ReactNode) => render(<SessionContext.Provider value={session}>{children}</SessionContext.Provider>);

beforeEach(() => {
  vi.spyOn(session.api, "summary").mockResolvedValue({ period, currencies: [{ currency: "INR", total_spent: "1234.560001", average_purchase: "1234.560001", purchase_count: 1, recorded_payment_total: "0" }] });
  vi.spyOn(session.api, "comparison").mockResolvedValue({ period, comparison_period: previous, currencies: [{ currency: "INR", current_total: "1234.560001", comparison_total: "0", absolute_change: "1234.560001", percentage_change: null }] });
  vi.spyOn(session.api, "categories").mockResolvedValue({ groups: [category], has_more: false });
  vi.spyOn(session.api, "merchants").mockResolvedValue({ groups: [], has_more: false });
  vi.spyOn(session.api, "trend").mockResolvedValue({ period, interval: "day", points: [] });
  vi.spyOn(session.api, "payments").mockResolvedValue({ period, groups: [] });
  vi.spyOn(session.api, "insights").mockResolvedValue([]);
});

it("keeps unknown and paginated category amounts distinct from recorded zero", () => {
  show(<CategoryComparison current={[category, { ...category, category_id: "unknown", category_name: "Unknown prices", total_amount: null }]} previous={[]} currency="INR" previousHasMore />);
  expect(screen.getAllByText("Unavailable")).toHaveLength(3);
  expect(screen.getByText("₹1,234.560001")).toBeTruthy();
  expect(screen.queryByText("₹0.00")).toBeNull();
});

it("exposes exact chart values and uses a single keyboard stop with arrow navigation", async () => {
  show(<TrendChart currency="INR" data={{ period, interval: "day", points: [
    { date: "2026-09-01", currency: "INR", total_spent: "1234.560001", purchase_count: 1 },
    { date: "2026-09-02", currency: "INR", total_spent: "0", purchase_count: 0 },
    { date: "2026-09-01", currency: "USD", total_spent: "999", purchase_count: 1 },
  ] }} />);
  const points = screen.getAllByRole("button");
  expect(points).toHaveLength(2);
  await userEvent.tab();
  expect(document.activeElement).toBe(points[0]);
  await userEvent.keyboard("{ArrowRight}");
  expect(document.activeElement).toBe(points[1]);
  await userEvent.keyboard("{Home}");
  expect(document.activeElement).toBe(points[0]);
  await userEvent.click(screen.getByText("View chart data"));
  expect(within(screen.getByRole("table")).getByText("₹1,234.560001")).toBeTruthy();
  expect(screen.queryByText(/999/)).toBeNull();
});

it("distinguishes unchanged spending from an unavailable comparison", () => {
  show(<><Change value="0.000000" /><Change value={null} /><Change value={undefined} /></>);
  expect(screen.getByText("No change")).toBeTruthy();
  expect(screen.getByText("No prior spending")).toBeTruthy();
  expect(screen.getByText("Comparison unavailable")).toBeTruthy();
});

it("uses the service's comparison boundaries and sends category filters to each analytics read", async () => {
  show(<Analysis />);
  await screen.findByText("Category comparison");
  expect(session.api.categories).toHaveBeenCalledWith(expect.objectContaining({ start_date: previous.start_date, end_date: previous.end_date, period: undefined }), expect.any(AbortSignal));
  await userEvent.selectOptions(screen.getByLabelText("Analysis category"), "food");
  await waitFor(() => expect(session.api.trend).toHaveBeenLastCalledWith(expect.objectContaining({ category_id: "food", currency: "INR" }), expect.any(AbortSignal)));
  expect(session.api.payments).toHaveBeenLastCalledWith(expect.objectContaining({ category_id: "food" }), expect.any(AbortSignal));
  await screen.findByText("Category comparison");
  vi.mocked(session.api.categories).mockResolvedValue({ groups: [], has_more: false });
  await userEvent.selectOptions(screen.getByLabelText("Time period"), "last_month");
  await screen.findByText("Category comparison");
  expect(screen.getByLabelText<HTMLSelectElement>("Analysis category").selectedOptions[0].text).toBe("Groceries");
  await userEvent.selectOptions(screen.getByLabelText("Time period"), "custom");
  await screen.findByText(/Choose a start and end date/);
  expect(screen.queryByText("Category comparison")).toBeNull();
});

it("shows a recoverable analytics failure without presenting stale totals", async () => {
  vi.mocked(session.api.trend).mockRejectedValueOnce(new Error("Trend unavailable"));
  show(<Analysis />);
  await screen.findByText("Trend unavailable");
  expect(screen.queryByText("₹1,234.560001")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: /Try again/ }));
  await screen.findByText("Category comparison");
  expect(screen.queryByRole("alert")).toBeNull();
});
