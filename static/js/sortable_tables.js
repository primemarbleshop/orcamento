(function () {
    const EXCLUDED_HEADER_SELECTOR = '.actions-cell, [data-sort="none"], .no-sort';

    function textFromCell(cell) {
        const control = cell.querySelector('input, select, textarea');
        if (control) {
            if (control.tagName === 'SELECT') {
                return control.options[control.selectedIndex]?.text || control.value || '';
            }
            return control.value || control.textContent || '';
        }
        return cell.textContent || '';
    }

    function normalizeText(value) {
        return String(value || '').trim().replace(/\s+/g, ' ');
    }

    function parseDate(value) {
        const text = normalizeText(value);
        const br = text.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})$/);
        if (br) {
            const year = br[3].length === 2 ? Number(`20${br[3]}`) : Number(br[3]);
            return new Date(year, Number(br[2]) - 1, Number(br[1])).getTime();
        }
        const iso = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
        if (iso) {
            return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3])).getTime();
        }
        return Number.NaN;
    }

    function parseNumber(value) {
        let text = normalizeText(value);
        if (!text) return Number.NaN;
        text = text
            .replace(/[^\d,.\-]/g, '')
            .replace(/\.(?=\d{3}(?:\D|$))/g, '')
            .replace(',', '.');
        if (!text || text === '-' || text === '.' || text === '-.') return Number.NaN;
        return Number(text);
    }

    function sortValue(cell) {
        const raw = normalizeText(textFromCell(cell));
        const date = parseDate(raw);
        if (!Number.isNaN(date)) return { type: 'number', value: date };
        const number = parseNumber(raw);
        if (!Number.isNaN(number) && /\d/.test(raw)) return { type: 'number', value: number };
        return {
            type: 'text',
            value: raw.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        };
    }

    function compareCells(rowA, rowB, columnIndex, direction) {
        const a = sortValue(rowA.cells[columnIndex]);
        const b = sortValue(rowB.cells[columnIndex]);
        let result;
        if (a.type === 'number' && b.type === 'number') {
            result = a.value - b.value;
        } else {
            result = String(a.value).localeCompare(String(b.value), 'pt-BR', {
                numeric: true,
                sensitivity: 'base'
            });
        }
        return direction === 'asc' ? result : -result;
    }

    function isSortableHeader(th) {
        const table = th.closest('table');
        const index = Array.from(th.parentElement.children).indexOf(th);
        if (!table || index < 0) return false;
        if (th.matches(EXCLUDED_HEADER_SELECTOR)) return false;
        if (th.querySelector('button, a, input, select, textarea')) return false;
        const title = normalizeText(th.textContent);
        if (!title) return false;
        const normalizedTitle = title.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        if (normalizedTitle === 'acoes') return false;
        return Array.from(table.tBodies || []).some((tbody) =>
            Array.from(tbody.rows).some((row) => row.cells[index] && !row.cells[index].hasAttribute('colspan'))
        );
    }

    function clearTableState(table, activeHeader) {
        table.querySelectorAll('thead th[aria-sort]').forEach((th) => {
            if (th !== activeHeader) th.setAttribute('aria-sort', 'none');
        });
    }

    function sortTable(table, columnIndex, direction, header) {
        Array.from(table.tBodies || []).forEach((tbody) => {
            const rows = Array.from(tbody.rows)
                .map((row, originalIndex) => ({ row, originalIndex }))
                .filter((item) => item.row.cells[columnIndex] && !item.row.cells[columnIndex].hasAttribute('colspan'));

            rows.sort((a, b) => {
                const result = compareCells(a.row, b.row, columnIndex, direction);
                return result || (a.originalIndex - b.originalIndex);
            });

            rows.forEach((item) => tbody.appendChild(item.row));
        });

        clearTableState(table, header);
        table.dataset.sortColumn = String(columnIndex);
        table.dataset.sortDirection = direction;
        header.setAttribute('aria-sort', direction === 'asc' ? 'ascending' : 'descending');
    }

    function prepareTable(table) {
        if (table.dataset.sortableReady === 'true') return;
        const headerRow = table.tHead?.rows?.[0];
        if (!headerRow || !table.tBodies?.length) return;

        Array.from(headerRow.cells).forEach((th, index) => {
            if (!isSortableHeader(th)) return;
            th.classList.add('sortable-header');
            th.tabIndex = 0;
            th.setAttribute('role', 'button');
            th.setAttribute('aria-sort', 'none');
            th.title = 'Clique para ordenar';

            const activate = () => {
                const currentColumn = table.dataset.sortColumn;
                const currentDirection = table.dataset.sortDirection || 'desc';
                const direction = currentColumn === String(index) && currentDirection === 'asc' ? 'desc' : 'asc';
                sortTable(table, index, direction, th);
            };

            th.addEventListener('click', activate);
            th.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    activate();
                }
            });
        });

        table.dataset.sortableReady = 'true';
    }

    function initSortableTables() {
        document.querySelectorAll('table').forEach(prepareTable);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSortableTables);
    } else {
        initSortableTables();
    }
})();
