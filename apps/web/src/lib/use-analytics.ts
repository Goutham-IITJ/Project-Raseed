import { useSession } from "@/components/app-provider";
import { useResource } from "./use-resource";
import type { Query } from "./types";

export function useAnalytics(query: Query, compareCategories = false) {
  const { api } = useSession();
  return useResource(async signal => {
    const [summary, comparison, categories, merchants, trend, payments] = await Promise.all([
      api.summary(query, signal), api.comparison(query, signal),
      api.categories({ ...query, limit: 100 }, signal), api.merchants({ ...query, limit: 100 }, signal),
      api.trend(query, signal), api.payments(query, signal),
    ]);
    const previousCategories = compareCategories ? await api.categories({
      ...query, period: undefined, start_date: comparison.comparison_period.start_date,
      end_date: comparison.comparison_period.end_date, limit: 100,
    }, signal) : undefined;
    return { summary, comparison, categories, merchants, trend, payments, previousCategories };
  }, JSON.stringify(query) + compareCategories);
}
