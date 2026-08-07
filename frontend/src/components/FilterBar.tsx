import { CATEGORY_LABELS, PRIORITY_LABELS } from "../lib/labels";
import type { Category, CategoryFilter, Priority, PriorityFilter } from "../types";

const CATEGORIES: CategoryFilter[] = ["all", ...(Object.keys(CATEGORY_LABELS) as Category[])];
const PRIORITIES: PriorityFilter[] = ["all", ...(Object.keys(PRIORITY_LABELS) as Priority[])];

interface Props {
  category: CategoryFilter;
  priority: PriorityFilter;
  onCategoryChange: (value: CategoryFilter) => void;
  onPriorityChange: (value: PriorityFilter) => void;
  total: number;
  visible: number;
  unresolved: number;
}

export function FilterBar({
  category,
  priority,
  onCategoryChange,
  onPriorityChange,
  total,
  visible,
  unresolved,
}: Props) {
  return (
    <section className="filter-bar" aria-label="Filters">
      <label htmlFor="filter-category">
        Category
        <select
          id="filter-category"
          value={category}
          onChange={(e) => onCategoryChange(e.target.value as CategoryFilter)}
        >
          {CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {value === "all" ? "All" : CATEGORY_LABELS[value]}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor="filter-priority">
        Priority
        <select
          id="filter-priority"
          value={priority}
          onChange={(e) => onPriorityChange(e.target.value as PriorityFilter)}
        >
          {PRIORITIES.map((value) => (
            <option key={value} value={value}>
              {value === "all" ? "All" : PRIORITY_LABELS[value]}
            </option>
          ))}
        </select>
      </label>
      <span className="filter-count" aria-live="polite">
        Showing {visible} of {total}
        {unresolved > 0 && (
          <span className="filter-note"> · {unresolved} not triaged yet, kept visible</span>
        )}
      </span>
    </section>
  );
}
