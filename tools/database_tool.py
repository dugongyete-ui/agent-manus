"""Database Tool - Query PostgreSQL databases with safety checks and parameterized queries."""

import csv
import io
import logging
import os
import re
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DESTRUCTIVE_PATTERNS = [
    r"\b(DROP|DELETE|TRUNCATE|ALTER|UPDATE|INSERT|CREATE|GRANT|REVOKE)\b",
    r"\bINTO\s+OUTFILE\b",
    r"\bLOAD\s+DATA\b",
    r";\s*(DROP|DELETE|TRUNCATE|ALTER|UPDATE|INSERT|CREATE)",
]

MAX_ROWS = 10000
MAX_EXPORT_ROWS = 100000


class DatabaseTool:
    def __init__(self, database_url: Optional[str] = None, read_only: bool = True, max_rows: int = MAX_ROWS):
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        self.read_only = read_only
        self.max_rows = max_rows
        self.query_history: list[dict] = []

    def _get_connection(self):
        if not self.database_url:
            raise ConnectionError("DATABASE_URL tidak ditemukan. Set environment variable DATABASE_URL.")
        return psycopg2.connect(self.database_url)

    def _check_safety(self, sql: str, allow_write: bool = False) -> Optional[str]:
        sql_upper = sql.strip().upper()

        if not allow_write and self.read_only:
            for pattern in DESTRUCTIVE_PATTERNS:
                if re.search(pattern, sql_upper):
                    return (
                        f"Query ditolak: mengandung operasi berbahaya. "
                        f"Hanya SELECT query yang diizinkan dalam mode read-only. "
                        f"Set allow_write=True untuk mengizinkan operasi tulis."
                    )

        if re.search(r"--", sql) or re.search(r"/\*", sql):
            cleaned = re.sub(r"'[^']*'", "", sql)
            if re.search(r"--", cleaned) or re.search(r"/\*", cleaned):
                return "Query ditolak: mengandung komentar SQL yang mencurigakan."

        return None

    async def execute(self, params: dict) -> str:
        action = params.get("action", "")

        try:
            if action == "query":
                return await self._execute_query(params)
            elif action == "list_tables":
                return await self._list_tables()
            elif action == "describe":
                return await self._describe_table(params)
            elif action == "stats":
                return await self._table_stats(params)
            elif action == "export_csv":
                return await self._export_csv(params)
            else:
                return (
                    f"Database tool siap. Aksi tersedia: query, list_tables, describe, stats, export_csv. "
                    f"Mode: {'read-only' if self.read_only else 'read-write'}."
                )
        except ConnectionError as e:
            logger.error(f"Database connection error: {e}")
            return f"Error koneksi database: {e}"
        except psycopg2.Error as e:
            logger.error(f"Database error: {e}")
            return f"Error database: {e}"
        except Exception as e:
            logger.error(f"Error tidak terduga: {e}")
            return f"Error: {e}"

    async def _execute_query(self, params: dict) -> str:
        sql = params.get("sql", "").strip()
        query_params = params.get("params", [])
        allow_write = params.get("allow_write", False)

        if not sql:
            return "Error: parameter 'sql' diperlukan."

        safety_msg = self._check_safety(sql, allow_write=allow_write)
        if safety_msg:
            logger.warning(f"Query ditolak: {sql}")
            return safety_msg

        logger.info(f"Menjalankan query: {sql[:200]}")

        conn = self._get_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, tuple(query_params) if query_params else None)

            if cur.description is None:
                affected = cur.rowcount
                conn.commit()
                self.query_history.append({"sql": sql, "rows_affected": affected})
                return f"Query berhasil dieksekusi. Baris terpengaruh: {affected}"

            rows = cur.fetchmany(self.max_rows)
            total_available = cur.rowcount if cur.rowcount >= 0 else len(rows)
            columns = [desc[0] for desc in cur.description]

            self.query_history.append({"sql": sql, "rows_returned": len(rows), "columns": columns})

            return self._format_query_results(columns, rows, total_available)
        finally:
            conn.close()

    async def _list_tables(self) -> str:
        sql = """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql)
            rows = cur.fetchall()

            if not rows:
                return "Tidak ada tabel ditemukan dalam database."

            lines = ["=== Daftar Tabel ===", ""]
            current_schema = ""
            for row in rows:
                schema = row["table_schema"]
                if schema != current_schema:
                    current_schema = schema
                    lines.append(f"Schema: {schema}")
                    lines.append("-" * 40)
                table_type = "VIEW" if row["table_type"] == "VIEW" else "TABLE"
                lines.append(f"  {row['table_name']} ({table_type})")

            lines.append("")
            lines.append(f"Total: {len(rows)} tabel/view")
            return "\n".join(lines)
        finally:
            conn.close()

    async def _describe_table(self, params: dict) -> str:
        table = params.get("table", "").strip()
        if not table:
            return "Error: parameter 'table' diperlukan."

        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', table):
            return "Error: nama tabel tidak valid."

        parts = table.split(".")
        if len(parts) == 2:
            schema, table_name = parts
        else:
            schema, table_name = "public", parts[0]

        conn = self._get_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("""
                SELECT column_name, data_type, character_maximum_length,
                       is_nullable, column_default, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, table_name))
            columns = cur.fetchall()

            if not columns:
                return f"Tabel '{table}' tidak ditemukan atau tidak memiliki kolom."

            cur.execute("""
                SELECT tc.constraint_name, tc.constraint_type, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = %s AND tc.table_name = %s
            """, (schema, table_name))
            constraints = cur.fetchall()

            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = %s AND tablename = %s
            """, (schema, table_name))
            indexes = cur.fetchall()

            lines = [f"=== Struktur Tabel: {table} ===", ""]
            lines.append(f"{'Kolom':<30} {'Tipe':<25} {'Nullable':<10} {'Default'}")
            lines.append("-" * 90)

            pk_columns = {c["column_name"] for c in constraints if c["constraint_type"] == "PRIMARY KEY"}

            for col in columns:
                name = col["column_name"]
                dtype = col["data_type"]
                if col["character_maximum_length"]:
                    dtype += f"({col['character_maximum_length']})"
                nullable = col["is_nullable"]
                default = col["column_default"] or ""
                if len(default) > 30:
                    default = default[:27] + "..."
                pk_marker = " [PK]" if name in pk_columns else ""
                lines.append(f"  {name:<28} {dtype:<25} {nullable:<10} {default}{pk_marker}")

            if constraints:
                lines.append("")
                lines.append("Constraints:")
                seen = set()
                for c in constraints:
                    key = (c["constraint_name"], c["constraint_type"])
                    if key not in seen:
                        seen.add(key)
                        lines.append(f"  {c['constraint_name']} ({c['constraint_type']}) - {c['column_name']}")

            if indexes:
                lines.append("")
                lines.append("Indexes:")
                for idx in indexes:
                    lines.append(f"  {idx['indexname']}")

            lines.append("")
            lines.append(f"Total kolom: {len(columns)}")
            return "\n".join(lines)
        finally:
            conn.close()

    async def _table_stats(self, params: dict) -> str:
        table = params.get("table", "").strip()
        if not table:
            return "Error: parameter 'table' diperlukan."

        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', table):
            return "Error: nama tabel tidak valid."

        conn = self._get_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute(f"SELECT COUNT(*) as total_rows FROM {table}")
            count_row = cur.fetchone()
            total_rows = count_row["total_rows"] if count_row else 0

            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                  AND table_schema NOT IN ('information_schema', 'pg_catalog')
                ORDER BY ordinal_position
            """, (table.split(".")[-1],))
            columns = cur.fetchall()

            lines = [f"=== Statistik Tabel: {table} ===", ""]
            lines.append(f"Total baris: {total_rows}")
            lines.append(f"Total kolom: {len(columns)}")
            lines.append("")

            numeric_types = {"integer", "bigint", "smallint", "numeric", "real", "double precision", "decimal"}
            for col in columns:
                col_name = col["column_name"]
                col_type = col["data_type"]

                if col_type in numeric_types:
                    try:
                        cur.execute(f"""
                            SELECT
                                MIN({col_name}) as min_val,
                                MAX({col_name}) as max_val,
                                AVG({col_name})::numeric(20,2) as avg_val,
                                SUM({col_name})::numeric(20,2) as sum_val,
                                COUNT({col_name}) as non_null_count,
                                COUNT(*) - COUNT({col_name}) as null_count
                            FROM {table}
                        """)
                        stats = cur.fetchone()
                        if stats:
                            lines.append(f"  {col_name} ({col_type}):")
                            lines.append(f"    MIN: {stats['min_val']}, MAX: {stats['max_val']}, AVG: {stats['avg_val']}, SUM: {stats['sum_val']}")
                            lines.append(f"    Non-null: {stats['non_null_count']}, Null: {stats['null_count']}")
                    except psycopg2.Error:
                        pass
                else:
                    try:
                        cur.execute(f"""
                            SELECT
                                COUNT({col_name}) as non_null_count,
                                COUNT(*) - COUNT({col_name}) as null_count,
                                COUNT(DISTINCT {col_name}) as distinct_count
                            FROM {table}
                        """)
                        stats = cur.fetchone()
                        if stats:
                            lines.append(f"  {col_name} ({col_type}):")
                            lines.append(f"    Non-null: {stats['non_null_count']}, Null: {stats['null_count']}, Distinct: {stats['distinct_count']}")
                    except psycopg2.Error:
                        pass

            return "\n".join(lines)
        finally:
            conn.close()

    async def _export_csv(self, params: dict) -> str:
        sql = params.get("sql", "").strip()
        output = params.get("output", "").strip()

        if not sql:
            return "Error: parameter 'sql' diperlukan."
        if not output:
            return "Error: parameter 'output' (nama file) diperlukan."

        safety_msg = self._check_safety(sql)
        if safety_msg:
            return safety_msg

        if not output.endswith(".csv"):
            output += ".csv"

        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql)

            if cur.description is None:
                return "Error: query tidak mengembalikan data untuk diekspor."

            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchmany(MAX_EXPORT_ROWS)

            os.makedirs(os.path.dirname(os.path.abspath(output)) if os.path.dirname(output) else ".", exist_ok=True)

            with open(output, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                for row in rows:
                    writer.writerow(row)

            file_size = os.path.getsize(output)
            logger.info(f"CSV diekspor: {output} ({len(rows)} baris, {file_size} bytes)")
            return (
                f"Data berhasil diekspor ke '{output}'.\n"
                f"Baris: {len(rows)}, Kolom: {len(columns)}\n"
                f"Ukuran file: {file_size} bytes\n"
                f"Kolom: {', '.join(columns)}"
            )
        finally:
            conn.close()

    def _format_query_results(self, columns: list, rows: list, total_available: int) -> str:
        if not rows:
            return "Query berhasil. Tidak ada data yang dikembalikan."

        lines = []
        col_widths = [len(str(c)) for c in columns]
        for row in rows[:50]:
            for i, col in enumerate(columns):
                val = str(row.get(col, ""))
                if len(val) > 50:
                    val = val[:47] + "..."
                col_widths[i] = max(col_widths[i], len(val))

        header = " | ".join(c.ljust(w) for c, w in zip(columns, col_widths))
        separator = "-+-".join("-" * w for w in col_widths)
        lines.append(header)
        lines.append(separator)

        display_rows = rows[:100]
        for row in display_rows:
            values = []
            for col, width in zip(columns, col_widths):
                val = str(row.get(col, ""))
                if len(val) > 50:
                    val = val[:47] + "..."
                values.append(val.ljust(width))
            lines.append(" | ".join(values))

        lines.append("")
        if len(rows) < total_available:
            lines.append(f"Menampilkan {len(display_rows)} dari {total_available} baris (dibatasi {self.max_rows}).")
        else:
            lines.append(f"Total: {len(display_rows)} baris.")

        return "\n".join(lines)

    def get_query_history(self, limit: int = 20) -> list[dict]:
        return self.query_history[-limit:]
