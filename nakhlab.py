import sys
import sqlite3
import jdatetime # Requires: pip install jdatetime
from datetime import timedelta
from PyQt6 import QtGui 
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QLineEdit, QPushButton, QLabel, QMessageBox, QTableWidget,
    QTableWidgetItem, QComboBox, QHeaderView, QDialog, QFormLayout, QListWidget, 
    QGroupBox, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, QSize, QMargins, QLocale

# --- Global Configuration and Database ---
DB_NAME = 'store_gym_db.db'
MANAGER_USERNAME = 'omid_kamali'
CLERK_USERNAME = 'clerk'
LOW_STOCK_THRESHOLD = 5 # آستانه هشدار اتمام موجودی

# --- Farsi Helpers and Shamsi Date Handling ---

def to_persian_numbers(text):
    """Converts Latin digits in text to Persian digits."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    mapping = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴', '5': '۵',
        '6': '۶', '7': '۷', '8': '۸', '9': '۹', '.': '.', ',': '،'
    }
    return ''.join(mapping.get(char, char) for char in text)

def from_persian_numbers(text):
    """Converts Persian digits in text to Latin digits, removes commas/grouping."""
    if not isinstance(text, str):
        return str(text)
    text = text.replace('،', '').replace(',', '').strip()
    mapping = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5',
        '۶': '6', '۷': '7', '۸': '8', '۹': '9'
    }
    return ''.join(mapping.get(char, char) for char in text)

def format_toman(amount):
    """Formats a number with thousands separators, Persian digits, and appends ' تومان'."""
    try:
        amount_float = float(amount)
        # Use an internal formatter to handle the separation correctly
        formatted = f'{amount_float:,.0f}'
        return to_persian_numbers(formatted) + " تومان"
    except (ValueError, TypeError):
        return "۰ تومان"

def get_current_shamsi_date_fa():
    """Returns current Shamsi date as a formatted, Persian-numbered string (YYYY/MM/DD)."""
    jd = jdatetime.datetime.now()
    date_str = jd.strftime('%Y/%m/%d')
    return to_persian_numbers(date_str)

def get_shamsi_date_after_days(days):
    """Calculates the Shamsi date 'days' after today and returns it as a formatted, Persian-numbered string (YYYY/MM/DD)."""
    future_jd = jdatetime.date.today() + timedelta(days=days)
    date_str = future_jd.strftime('%Y/%m/%d')
    return to_persian_numbers(date_str)

def parse_shamsi_date(date_fa):
    """Parses a Persian-numbered Shamsi date string (YYYY/MM/DD) into a jdatetime.date object."""
    end_date_latin = from_persian_numbers(date_fa).strip()
    if not end_date_latin:
        raise ValueError("تاریخ خالی است")
    
    parts = end_date_latin.split('/')
    if len(parts) != 3:
         raise ValueError("فرمت تاریخ صحیح نیست (YYYY/MM/DD)")

    try:
        year, month, day = map(lambda p: int(p.strip()), parts)
        # jdatetime validation
        jdatetime.date(year, month, day) 
        return jdatetime.date(year, month, day)
    except ValueError as e:
        raise ValueError(f"مقادیر تاریخ معتبر نیستند: {e}")

def is_date_expired(end_date_fa):
    """Compars the end date (Shamsi string YYYY/MM/DD) with today's date."""
    try:
        end_date_obj = parse_shamsi_date(end_date_fa)
        today_date_obj = jdatetime.date.today()
        return end_date_obj < today_date_obj
    except:
        return True

# --- Database Setup and Auth ---

def setup_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Store/Product Tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name_fa TEXT NOT NULL,
            stock_initial REAL NOT NULL,
            cost_fa REAL NOT NULL,
            price_fa REAL NOT NULL,
            total_sold REAL DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            sale_qty REAL NOT NULL,
            sale_price REAL NOT NULL,
            cost_price REAL NOT NULL,
            payment_method TEXT NOT NULL, 
            sale_date_fa TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        )
    ''')
    # Gym/Membership Tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memberships (
            id INTEGER PRIMARY KEY,
            member_number TEXT UNIQUE NOT NULL,
            name_fa TEXT NOT NULL,
            phone TEXT,
            start_date_fa TEXT NOT NULL,
            end_date_fa TEXT NOT NULL,
            paid_amount REAL NOT NULL,
            status TEXT NOT NULL 
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY,
            member_id INTEGER,
            date_fa TEXT NOT NULL,
            FOREIGN KEY (member_id) REFERENCES memberships (id) ON DELETE CASCADE
        )
    ''')
    # Users Table for Authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, 
            role TEXT NOT NULL 
        )
    ''')
    
    # Enable foreign keys for ON DELETE CASCADE to work
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Insert initial users if not present
    cursor.execute("SELECT COUNT(*) FROM users")
    is_first_run = cursor.fetchone()[0] == 0

    if is_first_run:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       (MANAGER_USERNAME, '1234', 'manager'))
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       (CLERK_USERNAME, '5678', 'clerk'))

    conn.commit()
    conn.close()
    return is_first_run

def show_initial_user_info():
    """Displays user info after QApplication is ready."""
    QMessageBox.information(None, "اطلاعات ورود", 
                            f"کاربران پیش فرض ایجاد شدند:\nمدیر (دسترسی کامل): {MANAGER_USERNAME} (1234)\nمنشی (دسترسی محدود): {CLERK_USERNAME} (5678)")

def authenticate_user(username, password):
    """Checks user credentials against the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# --- Custom Widgets and Delegates ---

class PersianInput(QLineEdit):
    """Custom QLineEdit for right-to-left text and right-alignment."""
    def __init__(self, placeholder=""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setFont(QtGui.QFont("B Nazanin", 11))
        self.setStyleSheet("padding: 5px;")

class PersianLabel(QLabel):
    """
    Custom QLabel for right-to-left text and right-alignment.
    Fix: Added 'style' argument to allow for custom CSS like margins.
    """
    def __init__(self, text, font_size=11, bold=False, color=None, style=None):
        super().__init__(text)
        font = QtGui.QFont("B Nazanin", font_size)
        font.setBold(bold)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        style_sheet = ""
        if color:
            style_sheet += f"color: {color};"
        
        # Apply custom style if provided (Fix for TypeError)
        if style:
            style_sheet += f" {style}"
            
        if style_sheet:
            self.setStyleSheet(style_sheet.strip())

class AlignRightDelegate(QStyledItemDelegate):
    """Ensures all items in a table column are right-aligned."""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

# --- Dialogs for CRUD Operations ---

class ProductEditDialog(QDialog):
    """Dialog for editing an existing product."""
    def __init__(self, product_id, initial_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"ویرایش کالای: {initial_data['name_fa']}")
        self.setFixedSize(400, 350)
        self.product_id = product_id
        self.conn = sqlite3.connect(DB_NAME)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.entries = {}
        
        # Define fields and placeholders
        fields = {
            "نام کالا:": (initial_data['name_fa'], ""),
            "موجودی اولیه:": (to_persian_numbers(initial_data['stock_initial']), "عدد"),
            "قیمت خرید (تومان):": (to_persian_numbers(initial_data['cost_fa']), "فقط عدد"),
            "قیمت فروش (تومان):": (to_persian_numbers(initial_data['price_fa']), "فقط عدد")
        }
        
        for label_text, (initial_value, placeholder) in fields.items():
            entry = PersianInput(placeholder=placeholder)
            entry.setText(initial_value)
            entry.setFixedWidth(200)
            form.addRow(PersianLabel(label_text), entry)
            self.entries[label_text] = entry

        # Display Total Sold (Read-only)
        sold_label = PersianLabel(to_persian_numbers(initial_data['total_sold']), font_size=12, bold=True, color='blue')
        form.addRow(PersianLabel("تعداد فروخته شده:"), sold_label)
        
        layout.addLayout(form)
        
        btn_save = QPushButton("ذخیره تغییرات")
        btn_save.clicked.connect(self.save_changes)
        btn_save.setMinimumHeight(40)
        layout.addWidget(btn_save)

    def save_changes(self):
        try:
            name = self.entries["نام کالا:"].text().strip()
            initial = float(from_persian_numbers(self.entries["موجودی اولیه:"].text()))
            cost = float(from_persian_numbers(self.entries["قیمت خرید (تومان):"].text()))
            price = float(from_persian_numbers(self.entries["قیمت فروش (تومان):"].text()))
            
            if not name or initial < 0 or cost < 0 or price < 0:
                QMessageBox.critical(self, "خطا", "لطفا تمام فیلدها را به درستی پر کنید و از اعداد مثبت استفاده کنید.")
                return

            cursor = self.conn.cursor()
            cursor.execute("UPDATE products SET name_fa=?, stock_initial=?, cost_fa=?, price_fa=? WHERE id=?",
                           (name, initial, cost, price, self.product_id))
            self.conn.commit()
            self.accept()
            
        except ValueError:
            QMessageBox.critical(self, "خطا", "مقادیر عددی را به درستی وارد کنید.")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در به‌روزرسانی کالا: {str(e)}")


class MembershipEditDialog(QDialog):
    """Dialog for editing an existing membership."""
    def __init__(self, member_id, initial_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"ویرایش عضویت: {initial_data['name_fa']} ({initial_data['member_number']})")
        self.setFixedSize(450, 450)
        self.member_id = member_id
        self.conn = sqlite3.connect(DB_NAME)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.entries = {}
        
        fields = {
            "شماره عضویت:": (initial_data['member_number'], "کد منحصر به فرد"),
            "نام عضو:": (initial_data['name_fa'], ""),
            "شماره تماس:": (initial_data['phone'], ""),
            "مبلغ پرداخت (تومان):": (to_persian_numbers(initial_data['paid_amount']), "فقط عدد"),
            "تاریخ شروع:": (initial_data['start_date_fa'], "مثال: ۱۴۰۲/۰۷/۱۵"),
            "تاریخ انقضا:": (initial_data['end_date_fa'], "مثال: ۱۴۰۲/۰۸/۱۵")
        }
        
        for label_text, (initial_value, placeholder) in fields.items():
            entry = PersianInput(placeholder=placeholder)
            entry.setText(initial_value)
            entry.setFixedWidth(200)
            # Make member number read-only to prevent unique constraint violations (use separate update if required)
            if label_text == "شماره عضویت:":
                 entry.setReadOnly(True) 
                 entry.setStyleSheet("background-color: #f0f0f0;")
            
            form.addRow(PersianLabel(label_text), entry)
            self.entries[label_text] = entry

        # Status ComboBox
        self.status_combo = QComboBox()
        self.status_combo.setFont(QtGui.QFont("B Nazanin", 11))
        self.status_combo.addItems(["فعال", "منقضی شده"])
        self.status_combo.setCurrentText(initial_data['status'])
        self.status_combo.setFixedWidth(200)
        form.addRow(PersianLabel("وضعیت:"), self.status_combo)

        layout.addLayout(form)
        
        btn_save = QPushButton("ذخیره تغییرات")
        btn_save.clicked.connect(self.save_changes)
        btn_save.setMinimumHeight(40)
        layout.addWidget(btn_save)

    def save_changes(self):
        try:
            # Note: member_number is read-only, so we just retrieve it.
            number = from_persian_numbers(self.entries["شماره عضویت:"].text())
            name = self.entries["نام عضو:"].text().strip()
            phone = from_persian_numbers(self.entries["شماره تماس:"].text())
            paid = float(from_persian_numbers(self.entries["مبلغ پرداخت (تومان):"].text()))
            start_date = self.entries["تاریخ شروع:"].text()
            end_date = self.entries["تاریخ انقضا:"].text()
            status = self.status_combo.currentText()

            if not all([number, name, start_date, end_date]) or paid < 0:
                QMessageBox.critical(self, "خطا", "لطفا تمام فیلدهای اصلی را به درستی پر کنید.")
                return

            parse_shamsi_date(start_date)
            parse_shamsi_date(end_date)
            
            cursor = self.conn.cursor()

            cursor.execute("UPDATE memberships SET name_fa=?, phone=?, paid_amount=?, start_date_fa=?, end_date_fa=?, status=? WHERE id=?",
                           (name, phone, paid, start_date, end_date, status, self.member_id))
            self.conn.commit()
            self.accept()
            
        except ValueError as ve:
            QMessageBox.critical(self, "خطا", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در به‌روزرسانی عضویت: {str(e)}")


# --- Store Tab Widget ---

class StoreTab(QWidget):
    def __init__(self, user_role, parent=None):
        super().__init__(parent)
        self.user_role = user_role
        self.conn = sqlite3.connect(DB_NAME)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        main_layout = QHBoxLayout(self)
        
        # --- Left Panel (Forms) ---
        
        form_panel = QWidget()
        form_panel.setFixedWidth(350)
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(0, 0, 10, 0)
        
        # 1. Product Form (Create)
        product_group = QGroupBox("ثبت کالای جدید")
        product_group.setFont(QtGui.QFont("B Nazanin", 12, QtGui.QFont.Weight.Bold))
        product_form = QFormLayout(product_group)
        product_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.product_entries = {
            "نام کالا:": PersianInput(), 
            "موجودی اولیه:": PersianInput(placeholder="فقط عدد"),
            "قیمت خرید (تومان):": PersianInput(placeholder="فقط عدد"),
            "قیمت فروش (تومان):": PersianInput(placeholder="فقط عدد")
        }
        for label, entry in self.product_entries.items():
            entry.setFixedWidth(150)
            product_form.addRow(PersianLabel(label), entry)
            
        btn_add_product = QPushButton("ثبت کالای جدید")
        btn_add_product.clicked.connect(self.add_product)
        product_form.addRow(btn_add_product)
        form_layout.addWidget(product_group)
        
        # 2. Sale Form
        sale_group = QGroupBox("ثبت فروش")
        sale_group.setFont(QtGui.QFont("B Nazanin", 12, QtGui.QFont.Weight.Bold))
        sale_form = QFormLayout(sale_group)
        sale_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.sale_product_combo = QComboBox()
        self.sale_product_combo.setFont(QtGui.QFont("B Nazanin", 11))
        self.sale_product_combo.setFixedWidth(150)
        
        self.sale_qty_input = PersianInput(placeholder="فقط عدد")
        self.sale_qty_input.setFixedWidth(150)
        
        self.sale_method_combo = QComboBox()
        self.sale_method_combo.setFont(QtGui.QFont("B Nazanin", 11))
        self.sale_method_combo.addItems(["نقد", "کارت"])
        self.sale_method_combo.setFixedWidth(150)
        
        self.sale_date_input = PersianInput(placeholder="مثال: ۱۴۰۲/۰۷/۱۵")
        self.sale_date_input.setText(get_current_shamsi_date_fa()) 
        self.sale_date_input.setFixedWidth(150)
        
        sale_form.addRow(PersianLabel("کالای فروخته شده:"), self.sale_product_combo)
        sale_form.addRow(PersianLabel("تعداد فروش:"), self.sale_qty_input)
        sale_form.addRow(PersianLabel("روش پرداخت:"), self.sale_method_combo)
        sale_form.addRow(PersianLabel("تاریخ فروش:"), self.sale_date_input)
        
        btn_record_sale = QPushButton("ثبت فروش")
        btn_record_sale.clicked.connect(self.record_sale)
        sale_form.addRow(btn_record_sale)
        form_layout.addWidget(sale_group)
        
        form_layout.addStretch(1)
        main_layout.addWidget(form_panel)

        # --- Right Panel (Alerts/List) ---
        
        list_panel = QVBoxLayout()
        
        # 3. Alerts Section (Top Row) - Low Stock Only
        alerts_hbox = QHBoxLayout()
        alerts_hbox.setSpacing(10)
        
        # Low Stock Alert
        self.low_stock_group = QGroupBox("⚠️ اخطار اتمام موجودی (کمتر از ۵)")
        self.low_stock_group.setFont(QtGui.QFont("B Nazanin", 11, QtGui.QFont.Weight.Bold))
        self.low_stock_group.setStyleSheet("QGroupBox::title { color: darkred; }")
        
        low_stock_layout = QVBoxLayout(self.low_stock_group)
        self.low_stock_list = QListWidget()
        self.low_stock_list.setFont(QtGui.QFont("B Nazanin", 11))
        self.low_stock_list.setStyleSheet("color: darkred; border: none; background: #ffebeb; padding: 5px;")
        low_stock_layout.addWidget(self.low_stock_list)
        
        alerts_hbox.addWidget(self.low_stock_group, 1)
        
        # Add stretch to occupy the space where Financial Summary used to be
        alerts_hbox.addStretch(1) 
        
        list_panel.addLayout(alerts_hbox)
        
        # 4. Products List
        list_panel.addWidget(PersianLabel("لیست کالاها و آمار", font_size=14, bold=True, color='#4f46e5'))
        
        # Setup Table (8 columns, 1st one hidden for DB ID)
        self.products_table = QTableWidget()
        self.products_table.setColumnCount(8)
        headers = ["DB_ID", "شماره", "نام کالا", "موجودی اولیه", "فروخته شده", "باقی‌مانده", "قیمت خرید (تومان)", "قیمت فروش (تومان)"]
        self.products_table.setHorizontalHeaderLabels(headers)
        self.products_table.setColumnHidden(0, True) # Hide the actual DB ID column
        
        self.products_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.products_table.verticalHeader().setVisible(False)
        self.products_table.setFont(QtGui.QFont("B Nazanin", 10))
        
        for col in range(8):
            delegate = AlignRightDelegate(self.products_table)
            self.products_table.setItemDelegateForColumn(col, delegate)
            
        list_panel.addWidget(self.products_table)
        
        # 5. CRUD Operation Buttons (Edit/Delete)
        crud_hbox = QHBoxLayout()
        self.btn_edit_product = QPushButton("✏️ ویرایش کالای انتخاب شده")
        self.btn_delete_product = QPushButton("🗑️ حذف کالای انتخاب شده")

        self.btn_edit_product.clicked.connect(self.open_edit_product_dialog)
        self.btn_delete_product.clicked.connect(self.delete_product)
        
        crud_hbox.addWidget(self.btn_edit_product)
        crud_hbox.addWidget(self.btn_delete_product)
        list_panel.addLayout(crud_hbox)
        
        main_layout.addLayout(list_panel)
        
        # Load initial data
        self.load_products()

    def reload_data(self):
        """Reloads all data components for the Store Tab."""
        self.load_products()

    def load_products(self):
        self.products_table.setRowCount(0)
        self.low_stock_list.clear()
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name_fa, stock_initial, cost_fa, price_fa, total_sold FROM products ORDER BY id DESC")
        rows = cursor.fetchall()
        
        product_names = []
        
        for row in rows:
            product_id, name, initial, cost, price, sold = row
            product_names.append(name)
            
            left = initial - sold
            
            # Low Stock Check
            if left < LOW_STOCK_THRESHOLD:
                self.low_stock_list.addItem(f"{name} - موجودی: {to_persian_numbers(left)}")
            
            row_position = self.products_table.rowCount()
            self.products_table.insertRow(row_position)
            
            # DB_ID (Column 0 - Hidden)
            self.products_table.setItem(row_position, 0, QTableWidgetItem(str(product_id)))
            
            # Display Rows (Columns 1-7)
            display_row = [
                to_persian_numbers(product_id), # "شماره" (1)
                name,                          # "نام کالا" (2)
                to_persian_numbers(initial),   # "موجودی اولیه" (3)
                to_persian_numbers(sold),      # "فروخته شده" (4)
                to_persian_numbers(left),      # "باقی‌مانده" (5)
                format_toman(cost),            # "قیمت خرید (تومان)" (6)
                format_toman(price)            # "قیمت فروش (تومان)" (7)
            ]
            
            for col, value in enumerate(display_row, start=1):
                item = QTableWidgetItem(value)
                # Highlight low stock row
                if left < LOW_STOCK_THRESHOLD and col == 5:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("darkred")))
                    item.setFont(QtGui.QFont("B Nazanin", 11, QtGui.QFont.Weight.Bold))

                self.products_table.setItem(row_position, col, item)
        
        # Update Sales ComboBox
        self.sale_product_combo.clear()
        self.sale_product_combo.addItems(product_names)
        conn.close()

    def add_product(self):
        try:
            name = self.product_entries["نام کالا:"].text().strip()
            initial = float(from_persian_numbers(self.product_entries["موجودی اولیه:"].text()))
            cost = float(from_persian_numbers(self.product_entries["قیمت خرید (تومان):"].text()))
            price = float(from_persian_numbers(self.product_entries["قیمت فروش (تومان):"].text()))
            
            if not name or initial < 0 or cost < 0 or price < 0:
                QMessageBox.critical(self, "خطا", "لطفا تمام فیلدها را به درستی پر کنید و از اعداد مثبت استفاده کنید.")
                return

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO products (name_fa, stock_initial, cost_fa, price_fa) VALUES (?, ?, ?, ?)",
                           (name, initial, cost, price))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "موفقیت", f"کالای '{name}' با موفقیت ثبت شد.")
            
            for entry in self.product_entries.values():
                entry.clear()
                
            self.load_products()
        except ValueError:
            QMessageBox.critical(self, "خطا", "مقادیر عددی (موجودی و قیمت) را به درستی و به صورت عدد وارد کنید.")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ثبت کالا: {str(e)}")

    def open_edit_product_dialog(self):
        selected_rows = self.products_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "هشدار", "لطفا یک کالا را از لیست انتخاب کنید.")
            return

        row = selected_rows[0].row()
        product_id = int(self.products_table.item(row, 0).text()) # Hidden DB ID
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name_fa, stock_initial, cost_fa, price_fa, total_sold FROM products WHERE id=?", (product_id,))
        p_id, name, initial, cost, price, sold = cursor.fetchone()
        conn.close()

        initial_data = {
            'name_fa': name,
            'stock_initial': initial,
            'cost_fa': cost,
            'price_fa': price,
            'total_sold': sold
        }

        dialog = ProductEditDialog(product_id, initial_data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_products()
            # No need to call financial summary here, it's done in AccountingTab when it gets activated
            QMessageBox.information(self, "موفقیت", "اطلاعات کالا با موفقیت به‌روز شد.")

    def delete_product(self):
        selected_rows = self.products_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "هشدار", "لطفا یک کالا را برای حذف انتخاب کنید.")
            return

        row = selected_rows[0].row()
        product_id = int(self.products_table.item(row, 0).text())
        product_name = self.products_table.item(row, 2).text()
        
        reply = QMessageBox.question(self, 'تأیید حذف', 
                                    f"آیا مطمئن هستید که می‌خواهید کالای '{product_name}' را حذف کنید؟\n(توجه: تمام سوابق فروش این کالا نیز حذف خواهند شد.)", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                # Due to FOREIGN KEY ON DELETE CASCADE on sales table, related sales are deleted automatically.
                cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
                conn.commit()
                conn.close()
                QMessageBox.information(self, "موفقیت", f"کالای '{product_name}' با موفقیت حذف شد.")
                self.load_products()
            except Exception as e:
                QMessageBox.critical(self, "خطا", f"خطا در حذف کالا: {str(e)}")
            
    def record_sale(self):
        try:
            product_name = self.sale_product_combo.currentText()
            qty = float(from_persian_numbers(self.sale_qty_input.text()))
            method = self.sale_method_combo.currentText()
            sale_date = self.sale_date_input.text() 
            
            if not product_name or qty <= 0 or not method or not sale_date:
                QMessageBox.critical(self, "خطا", "لطفا تمام فیلدهای فروش را پر کنید.")
                return

            parse_shamsi_date(sale_date) 
            sale_date_latin = from_persian_numbers(sale_date).strip() 

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            cursor.execute("SELECT id, stock_initial, cost_fa, price_fa, total_sold FROM products WHERE name_fa=?", (product_name,))
            product_info = cursor.fetchone()

            if not product_info:
                QMessageBox.critical(self, "خطا", "کالای انتخاب شده یافت نشد.")
                conn.close()
                return

            product_id, initial_stock, cost_price, sale_price, sold_qty = product_info
            current_stock = initial_stock - sold_qty

            if qty > current_stock:
                QMessageBox.warning(self, "هشدار موجودی", f"فقط {to_persian_numbers(current_stock)} عدد از این کالا موجود است. فروش ثبت نشد.")
                conn.close()
                return

            cursor.execute("INSERT INTO sales (product_id, sale_qty, sale_price, cost_price, payment_method, sale_date_fa) VALUES (?, ?, ?, ?, ?, ?)",
                           (product_id, qty, sale_price, cost_price, method, sale_date_latin))

            new_sold_qty = sold_qty + qty
            cursor.execute("UPDATE products SET total_sold=? WHERE id=?", (new_sold_qty, product_id))

            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "موفقیت", f"فروش '{to_persian_numbers(qty)}' عدد از کالای '{product_name}' ثبت شد.")
            
            self.sale_qty_input.clear()
            self.sale_date_input.setText(get_current_shamsi_date_fa())
            
            self.load_products()
            
        except ValueError as ve:
            QMessageBox.critical(self, "خطا", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ثبت فروش: {str(e)}")

# --- Accounting Tab Widget (NEW) ---

class AccountingTab(QWidget):
    def __init__(self, user_role, parent=None):
        super().__init__(parent)
        self.user_role = user_role
        self.conn = sqlite3.connect(DB_NAME)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        main_layout = QVBoxLayout(self)
        
        # Check RBAC - Only Manager can see this content
        if self.user_role != 'manager':
            main_layout.addWidget(PersianLabel("🚫 دسترسی محدود: برای مشاهده آمار مالی، نیاز به سطح دسترسی **«مدیر»** دارید.", 
                                                font_size=18, bold=True, color='red'))
            main_layout.addStretch(1)
            return

        # 1. Summary Box (Grid Layout)
        self.summary_group = QGroupBox("خلاصه مالی (تومان)")
        self.summary_group.setFont(QtGui.QFont("B Nazanin", 14, QtGui.QFont.Weight.Bold))
        self.summary_group.setStyleSheet("QGroupBox::title { color: #059669; }") # Green title
        
        summary_layout = QGridLayout(self.summary_group)
        self.summary_labels = {}
        # Changed titles for better visual grouping
        summary_titles = ["💰 سود خالص:", "💵 فروش نقدی:", "📉 زیان کلی:", "💳 فروش کارتی:"] 
        
        for i, title in enumerate(summary_titles):
            # 2 rows, 2 columns layout for summary
            row = i // 2
            col = i % 2
            
            label_title = PersianLabel(title, bold=True, font_size=12, color='darkgray')
            label_value = PersianLabel(format_toman(0), font_size=16, bold=True, color='navy')
            
            # Use different colors for emphasis
            if i == 0: label_value.setStyleSheet("color: #10b981;") # Green for profit
            if i == 2: label_value.setStyleSheet("color: #ef4444;") # Red for loss
            
            # Adding title and value to the grid (col*2+1 for title, col*2 for value)
            summary_layout.addWidget(label_title, row, col * 2 + 1, alignment=Qt.AlignmentFlag.AlignRight)
            summary_layout.addWidget(label_value, row, col * 2, alignment=Qt.AlignmentFlag.AlignLeft)
            
            self.summary_labels[title] = label_value
            
        main_layout.addWidget(self.summary_group)
        
        # 2. Detailed Sales Table
        # FIX: Added 'style' argument to PersianLabel call
        main_layout.addWidget(PersianLabel("لیست جزئیات فروش", font_size=14, bold=True, color='#4f46e5',
                                            style="margin-top: 15px;"))

        self.sales_table = QTableWidget()
        self.sales_table.setColumnCount(8)
        headers = ["ID", "تاریخ", "کالا", "تعداد", "روش پرداخت", "قیمت فروش (واحد)", "قیمت خرید (واحد)", "سود/زیان (کل)"]
        self.sales_table.setHorizontalHeaderLabels(headers)
        self.sales_table.setColumnHidden(0, True) 

        self.sales_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sales_table.verticalHeader().setVisible(False)
        self.sales_table.setFont(QtGui.QFont("B Nazanin", 10))
        
        for col in range(8):
            delegate = AlignRightDelegate(self.sales_table)
            self.sales_table.setItemDelegateForColumn(col, delegate)
            
        main_layout.addWidget(self.sales_table)
        
        # 3. Reset Button (Manager only)
        reset_hbox = QHBoxLayout()
        reset_hbox.addStretch(1)
        
        self.btn_reset_data = QPushButton("❌ ریست کامل آمار و داده‌ها (حذف همه سوابق)")
        self.btn_reset_data.setStyleSheet("""
            QPushButton {
                background-color: #f44336; /* Red */
                color: white;
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #e53935;
            }
        """)
        self.btn_reset_data.clicked.connect(self.reset_all_data)
        
        reset_hbox.addWidget(self.btn_reset_data)
        main_layout.addLayout(reset_hbox)
        
        # Load data
        self.calculate_financial_summary()
        self.load_sales_data()
        
    def reload_data(self):
        """Reloads all data components for the Accounting Tab."""
        self.calculate_financial_summary()
        self.load_sales_data()
        
    def calculate_financial_summary(self):
        cursor = self.conn.cursor()
        # Fetching data for sales table is enough, we will calculate here too
        cursor.execute("SELECT sale_qty, sale_price, cost_price, payment_method FROM sales")
        sales_data = cursor.fetchall()

        total_profit = 0
        total_loss = 0 
        total_cash = 0
        total_credit = 0

        for qty, s_price, c_price, method in sales_data:
            profit_per_unit = s_price - c_price
            total_sale_value = qty * s_price
            
            if profit_per_unit >= 0:
                total_profit += qty * profit_per_unit
            else:
                total_loss += qty * abs(profit_per_unit)
                
            if method == 'نقد':
                total_cash += total_sale_value
            elif method == 'کارت':
                total_credit += total_sale_value

        self.summary_labels["💰 سود خالص:"].setText(format_toman(total_profit - total_loss))
        self.summary_labels["📉 زیان کلی:"].setText(format_toman(total_loss))
        self.summary_labels["💵 فروش نقدی:"].setText(format_toman(total_cash))
        self.summary_labels["💳 فروش کارتی:"].setText(format_toman(total_credit))

    def load_sales_data(self):
        self.sales_table.setRowCount(0)
        
        cursor = self.conn.cursor()
        
        # Join sales with products to get the product name
        cursor.execute("""
            SELECT 
                s.id, s.sale_date_fa, p.name_fa, s.sale_qty, s.payment_method, 
                s.sale_price, s.cost_price 
            FROM sales s
            JOIN products p ON s.product_id = p.id
            ORDER BY s.id DESC
        """)
        rows = cursor.fetchall()
        
        for row in rows:
            sale_id, date, name, qty, method, s_price, c_price = row
            
            # Calculate total profit/loss for this sale item
            total_profit_loss = (s_price - c_price) * qty
            
            row_position = self.sales_table.rowCount()
            self.sales_table.insertRow(row_position)
            
            # DB_ID (Column 0 - Hidden)
            self.sales_table.setItem(row_position, 0, QTableWidgetItem(str(sale_id)))
            
            # Display Rows (Columns 1-7)
            display_row = [
                date,                                # "تاریخ" (1)
                name,                                # "کالا" (2)
                to_persian_numbers(qty),             # "تعداد" (3)
                method,                              # "روش پرداخت" (4)
                format_toman(s_price),               # "قیمت فروش (واحد)" (5)
                format_toman(c_price),               # "قیمت خرید (واحد)" (6)
                format_toman(total_profit_loss)      # "سود/زیان (کل)" (7)
            ]
            
            for col, value in enumerate(display_row, start=1):
                item = QTableWidgetItem(value)
                # Color code the profit/loss column
                if col == 7:
                    color = QtGui.QColor('#10b981') if total_profit_loss >= 0 else QtGui.QColor('#ef4444')
                    item.setForeground(QtGui.QBrush(color))
                    item.setFont(QtGui.QFont("B Nazanin", 11, QtGui.QFont.Weight.Bold))

                self.sales_table.setItem(row_position, col, item)
            
        self.calculate_financial_summary() # Update summary when sales are loaded

    def reset_all_data(self):
        """Deletes all sales, memberships, and attendance records, and resets total_sold in products."""
        
        # 1. First Confirmation
        reply = QMessageBox.warning(self, 'هشدار جدی: حذف کامل داده‌ها', 
                                    "آیا **واقعاً** مطمئن هستید که می‌خواهید تمام داده‌های فروش، اعضا و حضور و غیاب را حذف کنید؟ این عمل غیرقابل بازگشت است و تمام سوابق مالی شما را پاک می‌کند.", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.No:
            return

        # 2. Second Confirmation (extra safety)
        reply2 = QMessageBox.warning(self, 'تایید نهایی', 
                                    "این آخرین هشدار است. با تایید، تمام سوابق مالی و باشگاهی (فروش، اعضا، حضور) پاک شده و موجودی فروخته‌شده کالاها صفر می‌شود. آیا ادامه می‌دهید؟", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, 
                                     QMessageBox.StandardButton.Cancel)

        if reply2 == QMessageBox.StandardButton.Yes:
            try:
                cursor = self.conn.cursor()
                
                # 1. Clear Sales History
                cursor.execute("DELETE FROM sales")
                
                # 2. Reset Total Sold in Products table
                cursor.execute("UPDATE products SET total_sold = 0")
                
                # 3. Clear Gym Data
                cursor.execute("DELETE FROM attendance")
                cursor.execute("DELETE FROM memberships")
                
                self.conn.commit()
                
                QMessageBox.information(self, "موفقیت", "تمام داده‌های فروشگاه و باشگاه با موفقیت حذف و بازنشانی شدند. برنامه در حال به‌روزرسانی است.")
                
                # Notify MainWindow to reload all relevant tabs
                # FIX: Corrected parent access chain: AccountingTab -> QTabWidget -> QWidget(central) -> QMainWindow
                main_window = self.parent().parent().parent()
                if main_window: 
                     main_window.reload_all_tabs()
                
            except Exception as e:
                QMessageBox.critical(self, "خطا", f"خطا در حذف داده‌ها: {str(e)}")
        else:
            QMessageBox.information(self, "لغو عملیات", "عملیات حذف داده‌ها توسط شما لغو شد.")


# --- Gym Tab Widget ---

class GymTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn = sqlite3.connect(DB_NAME)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        main_layout = QHBoxLayout(self)
        
        # --- Left Panel (Forms) ---
        
        form_panel = QWidget()
        form_panel.setFixedWidth(350)
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(0, 0, 10, 0)
        
        # 1. Membership Form (Create)
        member_group = QGroupBox("ثبت عضویت جدید")
        member_group.setFont(QtGui.QFont("B Nazanin", 12, QtGui.QFont.Weight.Bold))
        member_form = QFormLayout(member_group)
        member_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.member_entries = {
            "شماره عضویت:": PersianInput(placeholder="کد منحصر به فرد"),
            "نام عضو:": PersianInput(),
            "شماره تماس:": PersianInput(),
            "مبلغ پرداخت (تومان):": PersianInput(placeholder="فقط عدد"),
            "تاریخ شروع:": PersianInput(placeholder="مثال: ۱۴۰۲/۰۷/۱۵"),
            "تاریخ انقضا:": PersianInput(placeholder="مثال: ۱۴۰۲/۰۸/۱۵")
        }
        
        self.member_entries["تاریخ شروع:"].setText(get_current_shamsi_date_fa())
        self.member_entries["تاریخ انقضا:"].setText(get_shamsi_date_after_days(30))
        
        for label, entry in self.member_entries.items():
            entry.setFixedWidth(150)
            member_form.addRow(PersianLabel(label), entry)
            
        btn_add_member = QPushButton("ثبت عضویت جدید")
        btn_add_member.clicked.connect(self.add_membership)
        member_form.addRow(btn_add_member)
        form_layout.addWidget(member_group)
        
        # 2. Attendance Form
        attendance_group = QGroupBox("ثبت حضور")
        attendance_group.setFont(QtGui.QFont("B Nazanin", 12, QtGui.QFont.Weight.Bold))
        attendance_form = QFormLayout(attendance_group)
        attendance_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.attendance_member_num = PersianInput(placeholder="شماره عضویت")
        self.attendance_member_num.setFixedWidth(150)
        self.attendance_date = PersianInput()
        self.attendance_date.setFixedWidth(150)
        self.attendance_date.setText(get_current_shamsi_date_fa())

        attendance_form.addRow(PersianLabel("شماره عضویت:"), self.attendance_member_num)
        attendance_form.addRow(PersianLabel("تاریخ:"), self.attendance_date)
        
        btn_record_attendance = QPushButton("ثبت حضور")
        btn_record_attendance.clicked.connect(self.record_attendance)
        attendance_form.addRow(btn_record_attendance)
        form_layout.addWidget(attendance_group)
        
        form_layout.addStretch(1)
        main_layout.addWidget(form_panel)

        # --- Right Panel (Alerts/List) ---
        
        list_panel = QVBoxLayout()
        
        # 3. Expiry Alert
        alert_group = QGroupBox("❌ اخطار اتمام عضویت (کمتر از ۷ روز)")
        alert_group.setFont(QtGui.QFont("B Nazanin", 11, QtGui.QFont.Weight.Bold))
        alert_group.setStyleSheet("QGroupBox::title { color: darkorange; }")
        alert_layout = QVBoxLayout(alert_group)
        self.expiry_list = QListWidget()
        self.expiry_list.setFont(QtGui.QFont("B Nazanin", 11))
        self.expiry_list.setStyleSheet("color: darkorange; border: none; background: #fffbe6; padding: 5px;")
        alert_layout.addWidget(self.expiry_list)
        list_panel.addWidget(alert_group)
        
        # 4. Members List
        list_panel.addWidget(PersianLabel("لیست اعضای باشگاه", font_size=14, bold=True, color='#4f46e5'))
        
        # Setup Table (9 columns, 1st one hidden for DB ID)
        self.members_table = QTableWidget()
        self.members_table.setColumnCount(10)
        headers = ["DB_ID", "شناسه", "شماره عضویت", "نام عضو", "شماره تماس", "تاریخ شروع", "تاریخ انقضا", "مبلغ پرداخت", "وضعیت", "روزهای حضور"]
        self.members_table.setHorizontalHeaderLabels(headers)
        self.members_table.setColumnHidden(0, True) # Hide the actual DB ID column

        self.members_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.members_table.verticalHeader().setVisible(False)
        self.members_table.setFont(QtGui.QFont("B Nazanin", 10))
        
        for col in range(10):
            delegate = AlignRightDelegate(self.members_table)
            self.members_table.setItemDelegateForColumn(col, delegate)
            
        list_panel.addWidget(self.members_table)
        
        # 5. CRUD Operation Buttons (Edit/Delete)
        crud_hbox = QHBoxLayout()
        self.btn_edit_member = QPushButton("✏️ ویرایش عضویت انتخاب شده")
        self.btn_delete_member = QPushButton("🗑️ حذف عضویت انتخاب شده")

        self.btn_edit_member.clicked.connect(self.open_edit_membership_dialog)
        self.btn_delete_member.clicked.connect(self.delete_membership)
        
        crud_hbox.addWidget(self.btn_edit_member)
        crud_hbox.addWidget(self.btn_delete_member)
        list_panel.addLayout(crud_hbox)
        
        main_layout.addLayout(list_panel)
        
        # Load initial data
        self.load_members()
    
    def reload_data(self):
        """Reloads all data components for the Gym Tab."""
        self.load_members()

    def load_members(self):
        self.members_table.setRowCount(0)
        self.expiry_list.clear()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Fetch Attendance Counts
        attendance_counts = {}
        cursor.execute("SELECT member_id, COUNT(id) FROM attendance GROUP BY member_id")
        for member_id, count in cursor.fetchall():
            attendance_counts[member_id] = count
            
        # 2. Fetch Members
        cursor.execute("SELECT id, member_number, name_fa, phone, start_date_fa, end_date_fa, paid_amount, status FROM memberships ORDER BY id DESC")
        members = cursor.fetchall()
        
        today_date_obj = jdatetime.date.today()
        one_week_later = today_date_obj + timedelta(days=7)
        member_number_counter = 0

        for row in members:
            db_id, number, name, phone, start, end, paid, status = row
            member_number_counter += 1 # Sequential display number
            attendance_count = attendance_counts.get(db_id, 0)
            
            # Check expiry and update status/tag if needed
            is_expired = is_date_expired(end)
            new_status = "منقضی شده" if is_expired else "فعال"
            
            if status != new_status:
                cursor.execute("UPDATE memberships SET status=? WHERE id=?", (new_status, db_id))
                conn.commit()
                status = new_status
            
            # Near expiry check (only for active members)
            if status == "فعال":
                try:
                    end_date_obj = parse_shamsi_date(end)
                    if today_date_obj <= end_date_obj <= one_week_later:
                         self.expiry_list.addItem(f"{name} ({number}) - انقضا: {end}")
                except:
                    pass
            
            paid_amount = 0.0
            try:
                paid_amount = float(paid)
            except (ValueError, TypeError):
                # Fallback to 0.0 if data is corrupt
                pass
                
            row_position = self.members_table.rowCount()
            self.members_table.insertRow(row_position)
            
            # DB_ID (Column 0 - Hidden)
            self.members_table.setItem(row_position, 0, QTableWidgetItem(str(db_id)))
            
            # Display Rows (Columns 1-9)
            display_row = [
                to_persian_numbers(member_number_counter), # "شناسه" (1) - Sequential number
                number,                         # "شماره عضویت" (2)
                name,                           # "نام عضو" (3)
                phone,                          # "شماره تماس" (4)
                start,                          # "تاریخ شروع" (5)
                end,                            # "تاریخ انقضا" (6)
                format_toman(paid_amount),      # "مبلغ پرداخت" (7)
                status,                         # "وضعیت" (8)
                to_persian_numbers(attendance_count) # "روزهای حضور" (9)
            ]
            
            for col, value in enumerate(display_row, start=1):
                item = QTableWidgetItem(value)
                # Color code the status column
                if col == 8: 
                    color = QtGui.QColor('red') if status == "منقضی شده" else QtGui.QColor('green')
                    item.setForeground(QtGui.QBrush(color))
                    item.setFont(QtGui.QFont("B Nazanin", 11, QtGui.QFont.Weight.Bold))
                self.members_table.setItem(row_position, col, item)
        
        conn.close()

    def add_membership(self):
        try:
            # We use Latin numbers for internal storage of 'number' since it's an ID
            number = from_persian_numbers(self.member_entries["شماره عضویت:"].text())
            name = self.member_entries["نام عضو:"].text().strip()
            phone = from_persian_numbers(self.member_entries["شماره تماس:"].text())
            paid = float(from_persian_numbers(self.member_entries["مبلغ پرداخت (تومان):"].text()))
            
            start_date = self.member_entries["تاریخ شروع:"].text()
            end_date = self.member_entries["تاریخ انقضا:"].text()

            if not all([number, name, start_date, end_date]) or paid < 0:
                QMessageBox.critical(self, "خطا", "لطفا تمام فیلدهای اصلی را به درستی پر کنید.")
                return

            parse_shamsi_date(start_date)
            parse_shamsi_date(end_date)
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM memberships WHERE member_number=?", (number,))
            if cursor.fetchone():
                QMessageBox.critical(self, "خطا", "شماره عضویت تکراری است.")
                conn.close()
                return

            status = "فعال"
            if is_date_expired(end_date):
                status = "منقضی شده"
            
            cursor.execute("INSERT INTO memberships (member_number, name_fa, phone, paid_amount, start_date_fa, end_date_fa, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (number, name, phone, paid, start_date, end_date, status))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "موفقیت", f"عضویت '{name}' با شماره '{number}' ثبت شد.")
            
            # Reset fields
            for entry in self.member_entries.values():
                 entry.clear()
            self.member_entries["تاریخ شروع:"].setText(get_current_shamsi_date_fa())
            self.member_entries["تاریخ انقضا:"].setText(get_shamsi_date_after_days(30)) 
            self.load_members()
            
        except ValueError as ve:
            QMessageBox.critical(self, "خطا", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ثبت عضویت: {str(e)}")

    def open_edit_membership_dialog(self):
        selected_rows = self.members_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "هشدار", "لطفا یک عضو را از لیست انتخاب کنید.")
            return

        row = selected_rows[0].row()
        member_id = int(self.members_table.item(row, 0).text()) # Hidden DB ID
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT member_number, name_fa, phone, start_date_fa, end_date_fa, paid_amount, status FROM memberships WHERE id=?", (member_id,))
        number, name, phone, start, end, paid, status = cursor.fetchone()
        conn.close()

        initial_data = {
            'member_number': number,
            'name_fa': name,
            'phone': phone,
            'start_date_fa': start,
            'end_date_fa': end,
            'paid_amount': paid,
            'status': status
        }

        dialog = MembershipEditDialog(member_id, initial_data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_members()
            QMessageBox.information(self, "موفقیت", "اطلاعات عضویت با موفقیت به‌روز شد.")

    def delete_membership(self):
        selected_rows = self.members_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "هشدار", "لطفا یک عضو را برای حذف انتخاب کنید.")
            return

        row = selected_rows[0].row()
        member_id = int(self.members_table.item(row, 0).text())
        member_name = self.members_table.item(row, 3).text()
        
        reply = QMessageBox.question(self, 'تأیید حذف', 
                                    f"آیا مطمئن هستید که می‌خواهید عضویت '{member_name}' را حذف کنید؟\n(توجه: تمام سوابق حضور این عضو نیز حذف خواهند شد.)", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                # Due to FOREIGN KEY ON DELETE CASCADE on attendance table, related attendances are deleted automatically.
                cursor.execute("DELETE FROM memberships WHERE id=?", (member_id,))
                conn.commit()
                conn.close()
                QMessageBox.information(self, "موفقیت", f"عضویت '{member_name}' با موفقیت حذف شد.")
                self.load_members()
            except Exception as e:
                QMessageBox.critical(self, "خطا", f"خطا در حذف عضویت: {str(e)}")

    def record_attendance(self):
        try:
            member_number = from_persian_numbers(self.attendance_member_num.text())
            attendance_date = self.attendance_date.text()

            if not member_number or not attendance_date:
                QMessageBox.critical(self, "خطا", "لطفا شماره عضویت و تاریخ حضور را وارد کنید.")
                return

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            cursor.execute("SELECT id, name_fa, end_date_fa FROM memberships WHERE member_number=?", (member_number,))
            member_info = cursor.fetchone()

            if not member_info:
                QMessageBox.critical(self, "خطا", f"شماره عضویت '{member_number}' یافت نشد.")
                conn.close()
                return

            member_id, member_name, end_date = member_info
            
            if is_date_expired(end_date):
                cursor.execute("UPDATE memberships SET status=? WHERE id=?", ("منقضی شده", member_id))
                conn.commit()
                self.load_members()
                QMessageBox.warning(self, "هشدار", f"عضویت '{member_name}' منقضی شده است. لطفاً ابتدا تمدید کنید.")
                conn.close()
                return

            parse_shamsi_date(attendance_date)
            
            cursor.execute("SELECT id FROM attendance WHERE member_id=? AND date_fa=?", (member_id, attendance_date))
            if cursor.fetchone():
                QMessageBox.information(self, "توجه", f"حضور '{member_name}' در تاریخ {attendance_date} قبلاً ثبت شده است.")
                conn.close()
                return

            cursor.execute("INSERT INTO attendance (member_id, date_fa) VALUES (?, ?)", (member_id, attendance_date))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "موفقیت", f"حضور '{member_name}' در تاریخ {attendance_date} ثبت شد.")
            
            self.attendance_member_num.clear()
            self.attendance_date.setText(get_current_shamsi_date_fa())
            
            self.load_members()

        except ValueError as ve:
            QMessageBox.critical(self, "خطا", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در ثبت حضور: {str(e)}")

# --- About Tab Widget (ENHANCED) ---

class AboutTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        # Main Container Styling
        container = QWidget()
        container.setMinimumWidth(800)
        container_layout = QVBoxLayout(container)
        container.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 2px solid #eef2ff;
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
            }
        """)

        # Title
        title = PersianLabel("نخلاب - سیستم مدیریت هوشمند", font_size=32, bold=True, color='#1e3a8a')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(title)
        
        # Separator (Aesthetics)
        separator = QLabel()
        separator.setMinimumHeight(4)
        separator.setStyleSheet("background-color: #a5b4fc; margin: 15px 0 25px 0; border-radius: 2px;")
        container_layout.addWidget(separator)

        # Mission Statement
        mission_title = PersianLabel("🚀 مأموریت ما: ادغام سادگی و قدرت", font_size=20, bold=True, color='#059669')
        container_layout.addWidget(mission_title)
        
        mission_text = """
        سامانه **نخلاب** با نگاهی نو به مدیریت کسب‌وکار، توسعه داده شده است. هدف اصلی، ارائه‌ی یک ابزار واحد و فوق‌العاده کاربردی برای مدیریت همزمان **بخش فروش کالا (Store)** و **بخش خدمات ورزشی (Gym)** است. ما باور داریم که نرم‌افزار باید پیچیدگی‌های روزمره را کاهش دهد، نه اینکه آن‌ها را افزایش دهد.
        نخلاب، راهکار سریع، ایمن و متمرکز بر **نقش‌های کاربر (مدیر/منشی)** است تا هرکس دقیقاً به همان داده‌هایی دسترسی داشته باشد که نیاز دارد.
        """
        mission_label = PersianLabel(mission_text, font_size=14, color='#374151')
        mission_label.setWordWrap(True)
        container_layout.addWidget(mission_label)
        
        # Features Group
        features_group = QGroupBox("✨ قابلیت‌های محوری")
        features_group.setFont(QtGui.QFont("B Nazanin", 16, QtGui.QFont.Weight.Bold))
        features_group.setStyleSheet("QGroupBox { margin-top: 30px; border: 1px solid #d1d5db; border-radius: 12px; padding: 15px; background-color: #f8fafc; } QGroupBox::title { color: #4338ca; padding: 0 10px; }")
        features_layout = QGridLayout(features_group)
        
        # Using a grid for feature presentation
        features = [
            ("🔐 امنیت نقش‌محور", "سیستم کنترل دسترسی قوی (RBAC) برای تفکیک وظایف مدیر و منشی."),
            ("📊 گزارش‌گیری پیشرفته", "جدول‌های شفاف و دقیق مالی برای محاسبه‌ی فوری سود خالص و تفکیک فروش."),
            ("📦 مدیریت هوشمند موجودی", "ردیابی دقیق کالاها، ثبت فروش لحظه‌ای و هشدار اتمام موجودی."),
            ("🗓️ رصد عضویت باشگاه", "مدیریت اعضا، تاریخ انقضا و ثبت حضور و غیاب روزانه.")
        ]
        
        for i, (title, desc) in enumerate(features):
            item_layout = QVBoxLayout()
            item_layout.addWidget(PersianLabel(title, bold=True, font_size=14, color='#4338ca'))
            item_layout.addWidget(PersianLabel(desc, font_size=12, color='#4b5563'))
            
            features_layout.addLayout(item_layout, i // 2, i % 2)

        container_layout.addWidget(features_group)
        
        # Contact Information (Footer)
        contact_title = PersianLabel("📞 تماس و پشتیبانی", font_size=18, bold=True, color='#ef4444', 
                                     style="margin-top: 25px;")
        container_layout.addWidget(contact_title)

        contact_info = PersianLabel("توسعه یافته توسط **تیم زیست دیجیتال** | برای کسب اطلاعات بیشتر به **zist.digital** مراجعه کنید.\nمجوز استفاده از نرم‌افزار: **AGPL 3**", 
                                     font_size=13, color='#6b7280', style="line-height: 1.8;")
        container_layout.addWidget(contact_info)

        main_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch(1)

# --- Login Window ---
# (Unchanged)

class LoginWindow(QDialog):
    """A dialog box for user authentication."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ورود به سامانه مدیریت")
        self.setFixedSize(350, 250)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.user_role = None 
        
        layout = QVBoxLayout(self)
        
        # Title
        title_label = PersianLabel("لطفاً نام کاربری و رمز عبور را وارد کنید", font_size=14, bold=True, color='#4f46e5')
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        form = QFormLayout()
        
        # Username Field
        self.username_input = PersianInput(placeholder="نام کاربری")
        self.username_input.setFixedWidth(180)
        form.addRow(PersianLabel("نام کاربری:"), self.username_input)
        
        # Password Field
        self.password_input = PersianInput(placeholder="رمز عبور")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setFixedWidth(180)
        form.addRow(PersianLabel("رمز عبور:"), self.password_input)
        
        layout.addLayout(form)
        
        # Login Button
        btn_login = QPushButton("ورود")
        btn_login.clicked.connect(self.handle_login)
        btn_login.setMinimumHeight(40)
        layout.addWidget(btn_login)

        self.setStyleSheet("""
            QDialog {
                background-color: #f8f8f8;
            }
            QPushButton {
                background-color: #4f46e5;
                color: white;
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #6366f1;
            }
            QPushButton:pressed {
                background-color: #4338ca;
            }
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 5px;
            }
        """)

    def handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        role = authenticate_user(username, password)
        
        if role:
            self.user_role = role
            self.accept() # Close dialog with accepted status (successful login)
        else:
            QMessageBox.critical(self, "خطای ورود", "نام کاربری یا رمز عبور اشتباه است.")
            self.password_input.clear() # Clear password field

# --- Main Window ---

class MainWindow(QMainWindow):
    def __init__(self, user_role):
        super().__init__()
        self.user_role = user_role
        self.setWindowTitle(f"سامانه مدیریت فروشگاه و باشگاه نخلاب - نقش: {'مدیر' if user_role == 'manager' else 'منشی'}")
        self.setMinimumSize(QSize(1200, 800))
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(QtGui.QFont("B Nazanin", 11, QtGui.QFont.Weight.Bold))
        
        # Add Tabs
        self.store_tab = StoreTab(user_role=self.user_role)
        self.gym_tab = GymTab()
        self.accounting_tab = AccountingTab(user_role=self.user_role) # NEW TAB
        self.about_tab = AboutTab()
        
        self.tab_widget.addTab(self.store_tab, "🏢 مدیریت فروشگاه و کالا")
        self.tab_widget.addTab(self.gym_tab, "🏋️ مدیریت باشگاه و اعضا")
        self.tab_widget.addTab(self.accounting_tab, "💰 حسابداری و آمار مالی") # NEW TAB TITLE
        self.tab_widget.addTab(self.about_tab, "ℹ️ درباره ما")
        
        # When switching tabs, ensure AccountingTab refreshes its data
        self.tab_widget.currentChanged.connect(self.tab_changed)

        main_layout = QVBoxLayout(self.central_widget)
        main_layout.addWidget(self.tab_widget)
        
        # Polished Styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f5; /* Light background */
            }
            QGroupBox {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 20px; 
                padding: 10px;
                background-color: #ffffff;
                box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.05);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top right;
                padding: 0 10px;
                background-color: #f0f0f0;
                border-radius: 5px;
            }
            QPushButton {
                background-color: #4f46e5;
                color: white;
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
                border: none;
                min-height: 35px;
            }
            QPushButton:hover {
                background-color: #6366f1;
            }
            QPushButton:pressed {
                background-color: #4338ca;
            }
            QTableWidget {
                border: 1px solid #ddd;
                gridline-color: #eee;
                background: #fff;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #eef2ff; /* Light blue header */
                padding: 8px;
                border: 1px solid #ddd;
                font-size: 11pt;
            }
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
                min-height: 35px;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)

    def reload_all_tabs(self):
        """Call reload method on all major functional tabs."""
        self.store_tab.reload_data()
        self.gym_tab.reload_data()
        if self.user_role == 'manager':
            self.accounting_tab.reload_data()

    def tab_changed(self, index):
        """Refreshes the accounting and other data when tabs are switched."""
        current_widget = self.tab_widget.widget(index)
        
        # Reload Accounting Tab only if manager is viewing it
        if current_widget == self.accounting_tab and self.user_role == 'manager':
            self.accounting_tab.reload_data()
        
        # Reload Store/Gym if they become active (important after a global reset)
        elif current_widget == self.store_tab:
            self.store_tab.reload_data()
        elif current_widget == self.gym_tab:
            self.gym_tab.reload_data()


# --- Application Entry Point ---

if __name__ == "__main__":
    
    app = QApplication(sys.argv)
    
    # Set the default application font to match the Persian font for consistency
    app_font = QtGui.QFont("B Nazanin")
    app_font.setPointSize(11)
    app.setFont(app_font)
    
    is_first_run = setup_db()
    
    # Show user info only if the database was just created
    if is_first_run:
        show_initial_user_info()
    
    login_dialog = LoginWindow()
    
    if login_dialog.exec() == QDialog.DialogCode.Accepted:
        user_role = login_dialog.user_role
        main_window = MainWindow(user_role)
        main_window.show()
        sys.exit(app.exec())
    else:
        # Exit application if login is cancelled
        sys.exit(0)

