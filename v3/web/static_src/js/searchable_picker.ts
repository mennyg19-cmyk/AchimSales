/** Searchable multi-select: one field + pills, same chrome as the customer picker. */

export type PickerItem = { key: string; name: string };

export type PickerOptions = {
  host: HTMLElement;
  pills: HTMLElement;
  placeholder?: string;
  formatOption?: (item: PickerItem) => string;
  formatPill?: (item: PickerItem) => string;
  onChange?: () => void;
};

const openPickers = new Set<SearchablePicker>();
let docBound = false;

function bindDocumentOnce(): void {
  if (docBound) return;
  docBound = true;
  document.addEventListener("click", (e) => {
    const t = e.target as Node;
    openPickers.forEach((p) => p.handleOutsideClick(t));
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") openPickers.forEach((p) => p.close());
  });
  window.addEventListener("scroll", () => openPickers.forEach((p) => p.reposition()), true);
  window.addEventListener("resize", () => openPickers.forEach((p) => p.reposition()));
}

export class SearchablePicker {
  private host: HTMLElement;
  private pills: HTMLElement;
  private placeholder: string;
  private formatOption: (item: PickerItem) => string;
  private formatPill: (item: PickerItem) => string;
  private onChange?: () => void;
  private items: PickerItem[] = [];
  private selected = new Map<string, string>();
  private isOpen = false;
  private search: HTMLInputElement;
  private list: HTMLElement;

  constructor(opts: PickerOptions) {
    this.host = opts.host;
    this.pills = opts.pills;
    this.placeholder = opts.placeholder || opts.host.dataset.placeholder || "Search…";
    this.formatOption = opts.formatOption || ((i) => i.name);
    this.formatPill = opts.formatPill || ((i) => i.name);
    this.onChange = opts.onChange;
    this.search = this.ensureSearch();
    this.list = this.ensureList();
    bindDocumentOnce();
    openPickers.add(this);
  }

  setOptions(items: PickerItem[]): void {
    this.items = items.slice();
    if (this.isOpen) this.renderOptions();
  }

  optionCount(): number {
    return this.items.length;
  }

  selectedKeys(): string[] {
    return [...this.selected.keys()];
  }

  setSelected(keys: string[]): void {
    this.selected.clear();
    keys.forEach((key) => {
      const row = this.items.find((i) => i.key === key);
      this.selected.set(key, row?.name || key);
    });
    this.renderPills();
    if (this.isOpen) this.renderOptions();
    this.onChange?.();
  }

  applyPending(keys: string[]): string[] {
    if (!keys.length || !this.items.length) return keys;
    this.setSelected(keys);
    return [];
  }

  clear(): void {
    this.selected.clear();
    this.search.value = "";
    this.close();
    this.renderPills();
    this.onChange?.();
  }

  close(): void {
    this.isOpen = false;
    this.list.hidden = true;
    this.search.setAttribute("aria-expanded", "false");
  }

  handleOutsideClick(target: Node): void {
    if (!this.isOpen) return;
    if (this.host.contains(target) || this.pills.contains(target)) return;
    this.close();
  }

  reposition(): void {
    if (!this.isOpen || this.list.hidden) return;
    const r = this.search.getBoundingClientRect();
    this.list.style.position = "fixed";
    this.list.style.top = `${Math.round(r.bottom + 2)}px`;
    this.list.style.left = `${Math.round(r.left)}px`;
    this.list.style.width = `${Math.round(r.width)}px`;
  }

  private ensureSearch(): HTMLInputElement {
    let search = this.host.querySelector<HTMLInputElement>(".customer-search");
    if (search) return search;
    this.host.innerHTML = "";
    search = document.createElement("input");
    search.type = "text";
    search.className = "customer-search";
    search.placeholder = this.placeholder;
    search.setAttribute("role", "combobox");
    search.setAttribute("aria-autocomplete", "list");
    search.setAttribute("aria-expanded", "false");
    search.setAttribute("aria-haspopup", "listbox");
    search.setAttribute("aria-label", this.placeholder);
    search.addEventListener("focus", () => this.open());
    search.addEventListener("input", () => this.open());
    search.addEventListener("keydown", (e) => this.onSearchKey(e));
    this.host.appendChild(search);
    return search;
  }

  private ensureList(): HTMLElement {
    let list = this.host.querySelector<HTMLElement>(".customer-options");
    if (list) return list;
    list = document.createElement("div");
    list.className = "customer-options";
    list.hidden = true;
    list.setAttribute("role", "listbox");
    list.id = `picker-list-${Math.random().toString(36).slice(2, 8)}`;
    this.host.appendChild(list);
    return list;
  }

  private open(): void {
    this.isOpen = true;
    this.search.setAttribute("aria-expanded", "true");
    this.search.setAttribute("aria-controls", this.list.id);
    this.renderOptions();
  }

  private onSearchKey(e: KeyboardEvent): void {
    if (e.key === "Escape") {
      this.close();
      return;
    }
    if (e.key === "ArrowDown" || e.key === "Enter") {
      e.preventDefault();
      this.open();
      const first = this.list.querySelector<HTMLInputElement>("input[type='checkbox']");
      first?.focus();
    }
  }

  private onOptionKey(e: KeyboardEvent, cb: HTMLInputElement): void {
    const boxes = [...this.list.querySelectorAll<HTMLInputElement>("input[type='checkbox']")];
    const i = boxes.indexOf(cb);
    if (e.key === "Escape") {
      e.preventDefault();
      this.close();
      this.search.focus();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      boxes[(i + 1) % boxes.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      boxes[(i - 1 + boxes.length) % boxes.length]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      boxes[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      boxes[boxes.length - 1]?.focus();
    }
  }

  private renderOptions(): void {
    const q = this.search.value.trim().toLowerCase();
    const matches = q
      ? this.items.filter(
          (i) => i.name.toLowerCase().includes(q) || i.key.toLowerCase().includes(q),
        )
      : this.items;
    this.list.innerHTML = "";
    matches.slice(0, 200).forEach((item) => {
      const row = document.createElement("label");
      row.className = "customer-option";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = this.selected.has(item.key);
      cb.addEventListener("keydown", (e) => this.onOptionKey(e, cb));
      cb.addEventListener("change", () => {
        if (cb.checked) this.selected.set(item.key, item.name);
        else this.selected.delete(item.key);
        this.renderPills();
        this.onChange?.();
      });
      row.appendChild(cb);
      const text = document.createElement("span");
      text.textContent = this.formatOption(item);
      row.appendChild(text);
      this.list.appendChild(row);
    });
    if (!matches.length) {
      const empty = document.createElement("div");
      empty.className = "customer-empty";
      empty.textContent = this.items.length ? "No matches" : "Loading…";
      this.list.appendChild(empty);
    }
    this.list.hidden = false;
    this.reposition();
  }

  private renderPills(): void {
    this.pills.innerHTML = "";
    this.selected.forEach((name, key) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "customer-chip";
      chip.textContent = `${this.formatPill({ key, name })} \u00d7`;
      chip.title = `Remove ${name}`;
      chip.addEventListener("click", () => {
        this.selected.delete(key);
        this.renderPills();
        if (this.isOpen) this.renderOptions();
        this.onChange?.();
      });
      this.pills.appendChild(chip);
    });
  }
}

export function pickerFromSelect(
  select: HTMLSelectElement,
  host: HTMLElement,
  pills: HTMLElement,
  extra?: Partial<PickerOptions>,
): SearchablePicker {
  const picker = new SearchablePicker({ host, pills, ...extra });
  const items: PickerItem[] = [...select.options].map((o) => ({
    key: o.value, name: (o.textContent || o.value).trim(),
  })).filter((i) => i.key);
  picker.setOptions(items);
  return picker;
}
