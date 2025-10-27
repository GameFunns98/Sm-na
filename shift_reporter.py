import json
import os
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
from typing import Dict, List, Tuple
import urllib.request
import urllib.error


APP_TITLE = "Shift Reporter"
INVENTORY_FILE = "inventory.json"
LOG_FILE = "shift_logs.json"
CONFIG_FILE = "config.json"

PRODUCTS: Dict[str, Dict[str, Dict[str, int]]] = {
    "Pivo": {"ingredients": {"Chmel": 1, "Ječmen": 1}},
    "Slivovice Meruňky": {"ingredients": {"Meruňky": 1}},
    "Slivovice Švestky": {"ingredients": {"Švestky": 1}},
}

DEFAULT_INVENTORY = {
    "Chmel": 0,
    "Ječmen": 0,
    "Meruňky": 0,
    "Švestky": 0,
}


class ShiftReporterApp:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title(APP_TITLE)
        self.master.resizable(False, False)

        self.start_time = datetime.now()
        self.end_time: datetime | None = None
        self.product_entries: List[Dict[str, object]] = []
        self.report_text: str | None = None

        self.inventory = self.load_inventory()

        self._build_ui()

    def load_inventory(self) -> Dict[str, int]:
        if not os.path.exists(INVENTORY_FILE):
            self.save_inventory(DEFAULT_INVENTORY.copy())
            return DEFAULT_INVENTORY.copy()

        try:
            with open(INVENTORY_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            messagebox.showwarning(
                APP_TITLE,
                "Nelze načíst inventory.json. Vytvářím nový soubor se základními hodnotami.",
            )
            self.save_inventory(DEFAULT_INVENTORY.copy())
            return DEFAULT_INVENTORY.copy()

        # Ensure all known ingredients exist
        for ingredient in DEFAULT_INVENTORY:
            data.setdefault(ingredient, DEFAULT_INVENTORY[ingredient])
        return data

    def save_inventory(self, inventory: Dict[str, int]) -> None:
        with open(INVENTORY_FILE, "w", encoding="utf-8") as fh:
            json.dump(inventory, fh, indent=2, ensure_ascii=False)

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        product_label = ttk.Label(main_frame, text="Produkt")
        product_label.grid(row=0, column=0, sticky="w")

        self.product_var = tk.StringVar(value=list(PRODUCTS.keys())[0])
        self.product_menu = ttk.Combobox(
            main_frame,
            textvariable=self.product_var,
            values=list(PRODUCTS.keys()),
            state="readonly",
            width=24,
        )
        self.product_menu.grid(row=1, column=0, sticky="ew", pady=(0, 5))

        qty_label = ttk.Label(main_frame, text="Množství")
        qty_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.quantity_var = tk.StringVar()
        self.quantity_entry = ttk.Entry(main_frame, textvariable=self.quantity_var, width=10)
        self.quantity_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 5))

        price_label = ttk.Label(main_frame, text="Cena za kus (Kč)")
        price_label.grid(row=0, column=2, sticky="w", padx=(10, 0))

        self.price_var = tk.StringVar()
        self.price_entry = ttk.Entry(main_frame, textvariable=self.price_var, width=12)
        self.price_entry.grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(0, 5))

        add_button = ttk.Button(main_frame, text="Add Product", command=self.add_product)
        add_button.grid(row=1, column=3, padx=(10, 0))

        columns = ("product", "quantity", "unit_price", "total_price")
        self.tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=8)
        self.tree.heading("product", text="Produkt")
        self.tree.heading("quantity", text="Množství")
        self.tree.heading("unit_price", text="Cena/Ks")
        self.tree.heading("total_price", text="Celkem")

        self.tree.column("product", width=160, anchor="w")
        self.tree.column("quantity", width=80, anchor="center")
        self.tree.column("unit_price", width=80, anchor="center")
        self.tree.column("total_price", width=80, anchor="center")

        self.tree.grid(row=2, column=0, columnspan=4, pady=10, sticky="nsew")

        totals_frame = ttk.Frame(main_frame)
        totals_frame.grid(row=3, column=0, columnspan=4, sticky="ew")

        self.total_cost_var = tk.StringVar(value="Celkem: 0 Kč")
        total_label = ttk.Label(totals_frame, textvariable=self.total_cost_var)
        total_label.pack(anchor="w")

        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=4, column=0, columnspan=4, pady=10, sticky="ew")

        end_shift_button = ttk.Button(
            buttons_frame,
            text="End Shift (Generate Report)",
            command=self.end_shift,
        )
        end_shift_button.pack(side="left")

        send_button = ttk.Button(
            buttons_frame,
            text="Send to Discord",
            command=self.send_to_discord,
        )
        send_button.pack(side="left", padx=10)

        report_label = ttk.Label(main_frame, text="Discord Report Preview")
        report_label.grid(row=5, column=0, columnspan=4, sticky="w")

        self.report_preview = tk.Text(main_frame, width=60, height=10, state="disabled")
        self.report_preview.grid(row=6, column=0, columnspan=4, sticky="ew")

        for child in main_frame.winfo_children():
            child.grid_configure(pady=2)

    def parse_quantity(self, value: str) -> int:
        try:
            quantity = int(value)
            if quantity <= 0:
                raise ValueError
            return quantity
        except ValueError:
            raise ValueError("Množství musí být kladné celé číslo.")

    def parse_price(self, value: str) -> float:
        try:
            price = float(value.replace(",", "."))
            if price < 0:
                raise ValueError
            return price
        except ValueError:
            raise ValueError("Cena musí být nezáporné číslo.")

    def add_product(self) -> None:
        product_name = self.product_var.get()
        try:
            quantity = self.parse_quantity(self.quantity_var.get())
            unit_price = self.parse_price(self.price_var.get())
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        ingredients = PRODUCTS[product_name]["ingredients"]
        required_ingredients: List[Tuple[str, int]] = []
        for ingredient_name, amount_per_unit in ingredients.items():
            required_amount = amount_per_unit * quantity
            available = self.inventory.get(ingredient_name, 0)
            if available < required_amount:
                messagebox.showerror(
                    APP_TITLE,
                    f"Nedostatek suroviny {ingredient_name}. K dispozici: {available}, potřeba: {required_amount}",
                )
                return
            required_ingredients.append((ingredient_name, required_amount))

        # Deduct ingredients and save inventory
        for ingredient_name, required_amount in required_ingredients:
            self.inventory[ingredient_name] = self.inventory.get(ingredient_name, 0) - required_amount
        self.save_inventory(self.inventory)

        total_price = quantity * unit_price
        entry = {
            "product": product_name,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price,
            "ingredients": required_ingredients,
        }
        self.product_entries.append(entry)
        self.tree.insert(
            "",
            "end",
            values=(
                entry["product"],
                entry["quantity"],
                f"{entry['unit_price']:.2f}",
                f"{entry['total_price']:.2f}",
            ),
        )

        self.quantity_var.set("")
        self.price_var.set("")
        self.update_totals()

    def update_totals(self) -> None:
        total_cost = sum(entry["total_price"] for entry in self.product_entries)
        self.total_cost_var.set(f"Celkem: {total_cost:.2f} Kč")

    def aggregate_usage(self) -> Tuple[Dict[str, int], Dict[str, int]]:
        ingredient_usage: Dict[str, int] = {}
        product_totals: Dict[str, int] = {}

        for entry in self.product_entries:
            product_totals[entry["product"]] = product_totals.get(entry["product"], 0) + entry["quantity"]
            for ingredient_name, required_amount in entry["ingredients"]:
                ingredient_usage[ingredient_name] = ingredient_usage.get(ingredient_name, 0) + required_amount

        return ingredient_usage, product_totals

    def format_line(self, label: str, value: int) -> str:
        dots_target = 25
        dotted_section = max(4, dots_target - len(label))
        return f"* **{label}** {'.' * dotted_section} {value}x"

    def build_report(self) -> str:
        if not self.product_entries:
            return f"{self.start_time.strftime('%H:%M')} - {datetime.now().strftime('%H:%M')}\nŽádné produkty nebyly zaznamenány."

        end_time = self.end_time or datetime.now()
        ingredient_usage, product_totals = self.aggregate_usage()
        total_cost = sum(entry["total_price"] for entry in self.product_entries)

        lines = [f"{self.start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"]
        if ingredient_usage:
            for ingredient_name in sorted(ingredient_usage):
                lines.append(self.format_line(ingredient_name, ingredient_usage[ingredient_name]))
        if product_totals:
            for product_name in sorted(product_totals):
                lines.append(self.format_line(product_name, product_totals[product_name]))

        lines.append(f"**Celkem:** {total_cost:.2f} Kč")
        return "\n".join(lines)

    def end_shift(self) -> None:
        if self.end_time is not None:
            messagebox.showinfo(APP_TITLE, "Směna již byla ukončena.")
            return

        self.end_time = datetime.now()
        report = self.build_report()
        self.report_text = report
        self.copy_to_clipboard(report)
        self.update_report_preview(report)
        self.append_shift_log(report)
        messagebox.showinfo(APP_TITLE, "Report byl vygenerován a zkopírován do schránky.")

    def copy_to_clipboard(self, text: str) -> None:
        self.master.clipboard_clear()
        self.master.clipboard_append(text)
        self.master.update_idletasks()

    def update_report_preview(self, report: str) -> None:
        self.report_preview.configure(state="normal")
        self.report_preview.delete("1.0", tk.END)
        self.report_preview.insert(tk.END, report)
        self.report_preview.configure(state="disabled")

    def append_shift_log(self, report: str) -> None:
        log_entry = {
            "start": self.start_time.isoformat(),
            "end": (self.end_time or datetime.now()).isoformat(),
            "products": self.product_entries,
            "report": report,
        }
        logs: List[Dict[str, object]]
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as fh:
                    logs = json.load(fh)
                    if not isinstance(logs, list):
                        logs = []
            except (json.JSONDecodeError, OSError):
                logs = []
        else:
            logs = []

        logs.append(log_entry)
        with open(LOG_FILE, "w", encoding="utf-8") as fh:
            json.dump(logs, fh, indent=2, ensure_ascii=False)

    def load_webhook_url(self) -> str | None:
        if not os.path.exists(CONFIG_FILE):
            return None
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return None
        webhook = data.get("webhook_url")
        if isinstance(webhook, str) and webhook.strip():
            return webhook.strip()
        return None

    def send_to_discord(self) -> None:
        if not self.report_text:
            messagebox.showwarning(APP_TITLE, "Nejprve vygenerujte report ukončením směny.")
            return
        webhook_url = self.load_webhook_url()
        if not webhook_url:
            messagebox.showerror(APP_TITLE, "Webhook URL není nastaveno v config.json.")
            return

        payload = json.dumps({"content": self.report_text}).encode("utf-8")
        request = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                if response.status != 204 and response.status != 200:
                    raise urllib.error.HTTPError(
                        webhook_url, response.status, "Neplatná odpověď", response.headers, None
                    )
        except urllib.error.HTTPError as exc:
            messagebox.showerror(APP_TITLE, f"Odeslání na Discord selhalo: {exc.code} {exc.reason}")
            return
        except urllib.error.URLError as exc:
            messagebox.showerror(APP_TITLE, f"Odeslání na Discord selhalo: {exc.reason}")
            return

        messagebox.showinfo(APP_TITLE, "Report byl odeslán na Discord.")


def main() -> None:
    root = tk.Tk()
    app = ShiftReporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
