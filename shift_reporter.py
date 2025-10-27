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
    "Pivo": {"ingredients": {"Chmel": 2, "Ječmen": 5}},
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
            messagebox.showwarning(APP_TITLE, "Nelze načíst inventory.json. Vytvářím nový soubor.")
            self.save_inventory(DEFAULT_INVENTORY.copy())
            return DEFAULT_INVENTORY.copy()

        for ingredient in DEFAULT_INVENTORY:
            data.setdefault(ingredient, DEFAULT_INVENTORY[ingredient])
        return data

    def save_inventory(self, inventory: Dict[str, int]) -> None:
        with open(INVENTORY_FILE, "w", encoding="utf-8") as fh:
            json.dump(inventory, fh, indent=2, ensure_ascii=False)

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # Typ položky
        type_label = ttk.Label(main_frame, text="Typ položky")
        type_label.grid(row=0, column=0, sticky="w")

        self.item_type_var = tk.StringVar(value="Produkt")
        type_menu = ttk.Combobox(
            main_frame,
            textvariable=self.item_type_var,
            values=["Produkt", "Surovina"],
            state="readonly",
            width=15,
        )
        type_menu.grid(row=1, column=0, sticky="ew", pady=(0, 5))

        # Výběr produktu/suroviny
        product_label = ttk.Label(main_frame, text="Název položky")
        product_label.grid(row=0, column=1, sticky="w")

        self.product_var = tk.StringVar(value=list(PRODUCTS.keys())[0])
        all_items = list(PRODUCTS.keys()) + list(DEFAULT_INVENTORY.keys())
        self.product_menu = ttk.Combobox(
            main_frame,
            textvariable=self.product_var,
            values=all_items,
            state="readonly",
            width=24,
        )
        self.product_menu.grid(row=1, column=1, sticky="ew", pady=(0, 5))

        qty_label = ttk.Label(main_frame, text="Množství")
        qty_label.grid(row=0, column=2, sticky="w", padx=(10, 0))

        self.quantity_var = tk.StringVar()
        self.quantity_entry = ttk.Entry(main_frame, textvariable=self.quantity_var, width=10)
        self.quantity_entry.grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(0, 5))

        price_label = ttk.Label(main_frame, text="Cena za kus (Kč)")
        price_label.grid(row=0, column=3, sticky="w", padx=(10, 0))

        self.price_var = tk.StringVar()
        self.price_entry = ttk.Entry(main_frame, textvariable=self.price_var, width=12)
        self.price_entry.grid(row=1, column=3, sticky="ew", padx=(10, 0), pady=(0, 5))

        add_button = ttk.Button(main_frame, text="Přidat položku", command=self.add_product)
        add_button.grid(row=1, column=4, padx=(10, 0))

        columns = ("product", "quantity", "unit_price", "total_price")
        self.tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=8)
        self.tree.heading("product", text="Položka")
        self.tree.heading("quantity", text="Množství")
        self.tree.heading("unit_price", text="Cena/Ks")
        self.tree.heading("total_price", text="Celkem")

        self.tree.column("product", width=160, anchor="w")
        self.tree.column("quantity", width=80, anchor="center")
        self.tree.column("unit_price", width=80, anchor="center")
        self.tree.column("total_price", width=80, anchor="center")
        self.tree.grid(row=2, column=0, columnspan=5, pady=10, sticky="nsew")

        totals_frame = ttk.Frame(main_frame)
        totals_frame.grid(row=3, column=0, columnspan=5, sticky="ew")

        self.total_cost_var = tk.StringVar(value="Celkem: 0 Kč")
        total_label = ttk.Label(totals_frame, textvariable=self.total_cost_var)
        total_label.pack(anchor="w")

        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=4, column=0, columnspan=5, pady=10, sticky="ew")

        end_shift_button = ttk.Button(buttons_frame, text="Ukončit směnu", command=self.end_shift)
        end_shift_button.pack(side="left")

        send_button = ttk.Button(buttons_frame, text="Odeslat na Discord", command=self.send_to_discord)
        send_button.pack(side="left", padx=10)

        report_label = ttk.Label(main_frame, text="Discord Report Náhled")
        report_label.grid(row=5, column=0, columnspan=5, sticky="w")

        self.report_preview = tk.Text(main_frame, width=70, height=10, state="disabled")
        self.report_preview.grid(row=6, column=0, columnspan=5, sticky="ew")

    def parse_quantity(self, value: str) -> int:
        try:
            q = int(value)
            if q <= 0:
                raise ValueError
            return q
        except ValueError:
            raise ValueError("Množství musí být kladné celé číslo.")

    def parse_price(self, value: str) -> float:
        try:
            p = float(value.replace(",", "."))
            if p < 0:
                raise ValueError
            return p
        except ValueError:
            raise ValueError("Cena musí být nezáporné číslo.")

    def add_product(self) -> None:
        item_type = self.item_type_var.get()
        item_name = self.product_var.get()
        try:
            quantity = self.parse_quantity(self.quantity_var.get())
            unit_price = self.parse_price(self.price_var.get() or "0")
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        if item_type == "Surovina":
            # Přidání do skladu
            self.inventory[item_name] = self.inventory.get(item_name, 0) + quantity
            self.save_inventory(self.inventory)
            total_price = quantity * unit_price
            entry = {
                "product": item_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "type": "Surovina",
                "ingredients": [],
            }

        else:
            # Produkt – výroba z ingrediencí
            ingredients = PRODUCTS.get(item_name, {}).get("ingredients", {})
            required_ingredients = []
            for ing_name, amount_per_unit in ingredients.items():
                needed = amount_per_unit * quantity
                available = self.inventory.get(ing_name, 0)
                if available < needed:
                    messagebox.showerror(APP_TITLE, f"Nedostatek suroviny {ing_name}.")
                    return
                required_ingredients.append((ing_name, needed))

            for ing_name, needed in required_ingredients:
                self.inventory[ing_name] -= needed
            self.save_inventory(self.inventory)

            total_price = quantity * unit_price
            entry = {
                "product": item_name,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "type": "Produkt",
                "ingredients": required_ingredients,
            }

        self.product_entries.append(entry)
        self.tree.insert("", "end",
                         values=(item_name, quantity, f"{unit_price:.2f}", f"{total_price:.2f}"))
        self.quantity_var.set("")
        self.price_var.set("")
        self.update_totals()

    def update_totals(self) -> None:
        total = sum(e["total_price"] for e in self.product_entries)
        self.total_cost_var.set(f"Celkem: {total:.2f} Kč")

    def aggregate_usage(self) -> Tuple[Dict[str, int], Dict[str, int]]:
        ingredients = {}
        products = {}
        additions = {}

        for entry in self.product_entries:
            if entry["type"] == "Surovina":
                additions[entry["product"]] = additions.get(entry["product"], 0) + entry["quantity"]
            else:
                products[entry["product"]] = products.get(entry["product"], 0) + entry["quantity"]
                for name, used in entry["ingredients"]:
                    ingredients[name] = ingredients.get(name, 0) + used
        return ingredients, products, additions

    def format_line(self, label: str, value: int) -> str:
        dots = max(4, 25 - len(label))
        return f"* **{label}** {'.' * dots} {value}x"

    def build_report(self) -> str:
        end_time = self.end_time or datetime.now()
        ing_use, prod_use, additions = self.aggregate_usage()
        total_cost = sum(e["total_price"] for e in self.product_entries)

        lines = [f"{self.start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"]
        if additions:
            lines.append("\n**📦 Nasbíráno:**")
            for k in sorted(additions):
                lines.append(self.format_line(k, additions[k]))
        if ing_use:
            lines.append("\n**⚙️ Spotřebováno:**")
            for k in sorted(ing_use):
                lines.append(self.format_line(k, ing_use[k]))
        if prod_use:
            lines.append("\n**🍺 Vyrobeno / Prodáno:**")
            for k in sorted(prod_use):
                lines.append(self.format_line(k, prod_use[k]))
        lines.append(f"\n**Celkem:** {total_cost:.2f} Kč")
        return "\n".join(lines)

    def end_shift(self) -> None:
        if self.end_time is not None:
            messagebox.showinfo(APP_TITLE, "Směna už byla ukončena.")
            return
        self.end_time = datetime.now()
        report = self.build_report()
        self.report_text = report
        self.copy_to_clipboard(report)
        self.update_report_preview(report)
        messagebox.showinfo(APP_TITLE, "Report vytvořen a zkopírován do schránky.")

    def copy_to_clipboard(self, text: str) -> None:
        self.master.clipboard_clear()
        self.master.clipboard_append(text)
        self.master.update_idletasks()

    def update_report_preview(self, report: str) -> None:
        self.report_preview.config(state="normal")
        self.report_preview.delete("1.0", tk.END)
        self.report_preview.insert("1.0", report)
        self.report_preview.config(state="disabled")

    def load_webhook_url(self) -> str | None:
        if not os.path.exists(CONFIG_FILE):
            return None
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data.get("webhook_url")
        except Exception:
            return None

    def send_to_discord(self) -> None:
        if not self.report_text:
            messagebox.showwarning(APP_TITLE, "Nejprve vygenerujte report.")
            return
        webhook = self.load_webhook_url()
        if not webhook:
            messagebox.showerror(APP_TITLE, "Webhook URL není nastaveno v config.json.")
            return
        payload = json.dumps({"content": self.report_text}).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req)
            messagebox.showinfo(APP_TITLE, "Report odeslán na Discord.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Odeslání selhalo: {e}")


def main() -> None:
    root = tk.Tk()
    app = ShiftReporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
