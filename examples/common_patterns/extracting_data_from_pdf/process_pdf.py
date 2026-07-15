import re  # Regular expressions for pattern matching
from pathlib import Path  # For handling file paths
import pdfplumber  # PDF processing library for extracting text and tables
from dateutil import parser as dateparser  # For parsing dates in various formats


class PDFInvoiceExtractor:
    """
    Class for extracting data from PDF invoices using pdfplumber and regex patterns.
    This class provides methods to extract invoice metadata, contact information, and financial totals from PDF files.
    You can modify this class to add more patterns or customize the extraction logic based on your specific invoice formats.
    """

    def __init__(self):
        """
        Initialize the extractor with compiled regex patterns.
        This includes patterns for invoice ID, dates, amounts, contact fields, and financial totals.
        The patterns are designed to match common invoice formats and can be extended as needed.
        """
        self.invoice_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in [
                r"INVOICE\s+Serial\s+No\.\s*([A-Za-z0-9\.\-]+)",
                r"Invoice\s*Serial\s*No\.\s*[:\-]?\s*(\S+)",
                r"Invoice\s*No\.?\s*[:#\-]?\s*(\S+)",
                r"Serial\s*No\.\s*[:\-]?\s*(\S+)",
            ]
        ]
        self.date_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in [
                r"Invoice\s+date[:\s]*([0-9]{4}[-/][0-9]{2}[-/][0-9]{2})",
                r"Invoice\s+date[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})",
                r"Invoice\s+date[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
            ]
        ]
        self.due_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in [
                r"Please pay until[:\s]*([0-9]{4}[-/][0-9]{2}[-/][0-9]{2})",
                r"Please pay until[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})",
                r"Due\s+date[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})",
                r"Due\s+date[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
            ]
        ]
        self.total_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in [
                r"Total amount[:\s]*([0-9\.,]+)",
                r"Total\s*amount\s*[:\s]*([0-9\.,]+)\s*€?",
                r"Total\s*due\s*[:\s]*([0-9\.,]+)",
            ]
        ]
        self.contact_fields = {
            "address": re.compile(r"Address[:\s]([^\n]+)", re.IGNORECASE),
            "email": re.compile(
                r"Email[:\s]*([a-zA-Z0-9._%+\-]{1,64}@[a-zA-Z0-9.\-]{1,255}\.[a-zA-Z]{2,})",
                re.IGNORECASE,
            ),
            "phone": re.compile(r"Phone[:\s]*([0-9\-\+\s\(\)]{1,30})", re.IGNORECASE),
            "code": re.compile(r"Code[:\s]*([0-9A-Za-z\-\_]{1,50})", re.IGNORECASE),
            "vat_code": re.compile(r"VAT\s*code[:\s]*([0-9A-Za-z\-\_]{1,30})", re.IGNORECASE),
            "amount_in_words": re.compile(r"Amount in words[:\s](.+)", re.IGNORECASE),
        }
        self.total_field_patterns = {
            "discount": re.compile(r"Total\s*discount", re.IGNORECASE),
            "taxable_amount": re.compile(r"Taxable\s*amount", re.IGNORECASE),
            "tax_rate": re.compile(r"Tax\s*rate", re.IGNORECASE),
            "total_taxes": re.compile(r"Total\s*taxes", re.IGNORECASE),
            "shipping": re.compile(r"Shipping", re.IGNORECASE),
            "total_amount": re.compile(r"Total\s*amount", re.IGNORECASE),
        }
        self.number_pattern = re.compile(r"([0-9\.,]+)")
        self.tax_rate_pattern = re.compile(r"(\d{1,3})\%?")

    @staticmethod
    def normalize_number(string):
        """
        Convert string representations of numbers into float values.
        This method handles various formats including currency symbols, commas, and decimal points.
        It also ensures that only the last decimal point is considered if multiple are present.
        You can extend this method to handle more complex number formats as needed.
        Args:
            string: String containing a number
        Returns:
            Float value of the number or None if conversion fails
        """
        if string is None:
            return None
        try:
            # Remove currency symbols and whitespace
            clean_s = re.sub(r"[^\d.,\-]", "", string.replace(",", "."))
            # Handle multiple decimal points (take the last one as decimal)
            parts = clean_s.split(".")
            if len(parts) > 2:
                clean_s = "".join(parts[:-1]) + "." + parts[-1]
            return float(clean_s)
        except Exception:
            return None

    @staticmethod
    def parse_iso_date(string):
        """
        Parse various date formats into ISO date string (YYYY-MM-DD).
        Args:
            string: String containing a date in various formats
        Returns:
            ISO formatted date string or None if parsing fails
        """
        if not string:
            return None
        try:
            d = dateparser.parse(string, dayfirst=False)
            return d.date().isoformat()
        except Exception:
            return None

    @staticmethod
    def safe_regex_extract(pattern, text, group=1):
        """
        Safely extract data using compiled regex pattern.
        Args:
            pattern: Compiled regular expression pattern
            text: Text to search in
            group: Capture group to extract (default: 1)
            Group 0 represents the entire match, while group 1 represents specific parenthesized capture groups.
        Returns:
            Extracted string or None if no match
        """
        try:
            match = pattern.search(text)
            if match:
                return match.group(group).strip()
            return None
        except Exception:
            return None

    def extract_using_patterns(self, text, patterns):
        """
        Try multiple compiled regex patterns to extract a value.
        Args:
            text: Text to search in
            patterns: List of compiled regex patterns to try
        Returns:
            First matched value or None if no match
        """
        for pattern in patterns:
            value = self.safe_regex_extract(pattern, text)
            if value:
                return value
        return None

    @staticmethod
    def extract_text_from_pdf(pdf):
        """
        Extract text from all pages of a PDF.
        Args:
            pdf: An open pdfplumber PDF object
        Returns:
            String containing all text content
        """
        pages_text = []

        for page in pdf.pages:
            try:
                text = page.extract_text() or ""
                pages_text.append(text)
            except Exception:
                pages_text.append("")

        return "\n".join(pages_text)

    @staticmethod
    def extract_tables_from_pdf(pdf):
        """
        Extract and clean tables from all pages of a PDF.
        Args:
            pdf: An open pdfplumber PDF object
        Returns:
            List of tables organized by page
        """
        tables_all = []

        for page in pdf.pages:
            try:
                raw_tables = page.extract_tables() or []
            except Exception:
                raw_tables = []

            cleaned_tables = []
            for t in raw_tables:
                cleaned = [
                    [
                        (
                            cell.strip()
                            if isinstance(cell, str)
                            else (str(cell).strip() if cell is not None else "")
                        )
                        for cell in row
                    ]
                    for row in t
                ]
                cleaned_tables.append(cleaned)
            tables_all.append(cleaned_tables)

        return tables_all

    def extract_text_and_tables(self, pdf_path):
        """
        Extract full text and tables from PDF.
        Args:
            pdf_path: Path to PDF file
        Returns:
            Tuple containing:
              - Full text content as string
              - List of tables by page
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                full_text = self.extract_text_from_pdf(pdf)
                tables_all = self.extract_tables_from_pdf(pdf)
                return full_text, tables_all
        except Exception as e:
            raise ValueError(f"Could not extract content from PDF: {e}")

    def extract_invoice_metadata(self, text):
        """
        Extract core invoice metadata like ID, dates, and amounts.
        This method uses predefined regex patterns to find and extract relevant information from the raw text.
        You can extend the method to match your specific invoice formats.
        Args:
            text: Raw text content from PDF
        Returns:
            Dictionary of extracted invoice metadata
        """
        result = {}

        # Extract invoice ID
        result["invoice_id"] = self.extract_using_patterns(text, self.invoice_patterns)

        # Extract dates
        raw_invoice_date = self.extract_using_patterns(text, self.date_patterns)
        result["invoice_date"] = self.parse_iso_date(raw_invoice_date)
        raw_due_date = self.extract_using_patterns(text, self.due_patterns)
        result["due_date"] = self.parse_iso_date(raw_due_date)

        # Extract total amount
        raw_total = self.extract_using_patterns(text, self.total_patterns)
        result["total_amount"] = self.normalize_number(raw_total)

        return result

    def extract_contact_info(self, text):
        """
        Extract contact information from invoice.
        You can extend this method to include more fields or modify existing patterns
        Args:
            text: Raw text content from PDF
        Returns:
            Dictionary of extracted contact information
        """
        result = {}
        for field, pattern in self.contact_fields.items():
            result[field] = self.safe_regex_extract(pattern, text)
        return result

    def _extract_tax_rate(self, line):
        """
        Extract tax rate from a line of text.
        Args:
            line: A single line of text
        Returns:
            Extracted tax rate as int or float, or None if not found
        """
        m = self.tax_rate_pattern.search(line)
        if not m:
            return None

        try:
            return int(m.group(1))
        except ValueError:
            return self.normalize_number(m.group(1))

    def _extract_standard_number(self, line):
        """
        Extract a standard number value from a line of text.
        Args:
            line: A single line of text
        Returns:
            Normalized number value or None if not found
        """
        m = self.number_pattern.search(line)
        return self.normalize_number(m.group(1)) if m else None

    def extract_totals(self, text):
        """
        Extract financial totals from invoice text.
        Args:
            text: Raw text content from PDF
        Returns:
            Dictionary of extracted totals information
        """
        totals = {}
        lines = [line.strip() for line in text.splitlines()]

        for line in lines:
            for field, pattern in self.total_field_patterns.items():
                # Skip if already found
                if field in totals and totals[field] is not None:
                    continue

                if not pattern.match(line):
                    continue

                # Extract value based on field type
                if field == "tax_rate":
                    totals[field] = self._extract_tax_rate(line)
                else:
                    totals[field] = self._extract_standard_number(line)

        return totals

    def process_pdf(self, pdf_path):
        """
        Process a PDF file and return extracted information as a JSON-serializable dictionary.
        This method is the main entry point for processing a PDF invoice.
        It extracts text, tables, invoice metadata, contact information, and totals.
        It also handles errors and ensures that the PDF file exists before processing.
        Args:
            pdf_path: Path to the PDF file
        Returns:
            Dictionary containing extracted information
        """
        try:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            # Extract text and tables
            full_text, tables_all = self.extract_text_and_tables(pdf_path)

            # Initialize result dictionary
            result = {}

            # Extract invoice metadata
            invoice_metadata = self.extract_invoice_metadata(full_text)
            result.update(invoice_metadata)

            # Extract contact information
            contact_info = self.extract_contact_info(full_text)
            result.update(contact_info)

            # Add page count of the pdf invoice
            result["pages"] = len(tables_all)

            # Extract totals information
            totals = self.extract_totals(full_text)
            result.update(totals)

            result["raw_text"] = full_text

            return result

        except Exception as e:
            raise RuntimeError(f"Failed to process PDF: {e}")
