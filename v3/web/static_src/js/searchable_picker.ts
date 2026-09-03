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
let pickerNumber = 0;

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
  private activeKey: string | null = null;

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
    this.setActive(null);
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
    search.addEventListener("focus", () => this.open());
    search.addEventListener("input", () => this.open());
    search.addEventListener("keydown", (event) => this.handleKeydown(event));
    this.host.appendChild(search);
    return search;
  }

  private ensureList(): HTMLElement {
    let list = this.host.querySelector<HTMLElement>(".customer-options");
    if (list) return list;
    list = document.createElement("div");
    list.className = "customer-options";
    list.id = `searchable-picker-${++pickerNumber}`;
    list.setAttribute("role", "listbox");
    list.hidden = true;
    this.search.setAttribute("aria-controls", list.id);
    this.host.appendChild(list);
    return list;
  }

  private open(): void {
    this.isOpen = true;
    this.renderOptions();
  }

  private handleKeydown(event: KeyboardEvent): void {
    const options = this.visibleOptions();
    if (event.key === "Escape") {
      if (!this.isOpen) return;
      event.preventDefault();
      this.close();
      this.search.focus();
      return;
    }
    if (!options.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      this.open();
      const activeIndex = options.findIndex((item) => item.key === this.activeKey);
      const nextIndex = event.key === "ArrowDown"
        ? Math.min(activeIndex + 1, options.length - 1)
        : Math.max(activeIndex - 1, 0);
      this.setActive(options[nextIndex].key);
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      this.open();
      this.setActive(options[event.key === "Home" ? 0 : options.length - 1].key);
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && this.activeKey) {
      event.preventDefault();
      const item = options.find((option) => option.key === this.activeKey);
      if (item) this.toggle(item);
    }
  }

  private visibleOptions(): PickerItem[] {
    const query = this.search.value.trim().toLowerCase();
    const matches = query
      ? this.items.filter((item) => item.name.toLowerCase().includes(query) || item.key.toLowerCase().includes(query))
      : this.items;
    return matches.slice(0, 200);
  }

  private setActive(key: string | null): void {
    this.activeKey = key;
    if (key) this.search.setAttribute("aria-activedescendant", `${this.list.id}-option-${key}`);
    else this.search.removeAttribute("aria-activedescendant");
    this.list.querySelectorAll<HTMLElement>(".customer-option").forEach((option) => {
      option.classList.toggle("is-active", option.id === `${this.list.id}-option-${key}`);
    });
    this.list.querySelector<HTMLElement>(".customer-option.is-active")?.scrollIntoView({ block: "nearest" });
  }

  private toggle(item: PickerItem): void {
    if (this.selected.has(item.key)) this.selected.delete(item.key);
    else this.selected.set(item.key, item.name);
    this.renderPills();
    this.renderOptions();
    this.onChange?.();
    this.search.focus();
  }

  private renderOptions(): void {
    const matches = this.visibleOptions();
    if (!matches.some((item) => item.key === this.activeKey)) this.activeKey = null;
    this.list.innerHTML = "";
    matches.forEach((item) => {
      const row = document.createElement("label");
      row.className = "customer-option";
      row.id = `${this.list.id}-option-${item.key}`;
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", String(this.selected.has(item.key)));
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.tabIndex = -1;
      cb.checked = this.selected.has(item.key);
      cb.addEventListener("change", () => {
        this.activeKey = item.key;
        if (cb.checked) this.selected.set(item.key, item.name);
        else this.selected.delete(item.key);
        this.renderPills();
        this.renderOptions();
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
    this.search.setAttribute("aria-expanded", "true");
    this.setActive(this.activeKey);
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
