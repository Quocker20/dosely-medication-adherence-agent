import { useEffect, useId, useMemo, useRef, useState } from "react";
import { api } from "../../../api";
import type { MedicationDetail } from "../../../types";

interface Props {
  medications: MedicationDetail[];
  selectedId: string;
  onSelect: (medication: MedicationDetail | null) => void;
  disabled?: boolean;
  placeholder?: string;
}

function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .trim();
}

export default function MedicationCombobox({
  medications,
  selectedId,
  onSelect,
  disabled = false,
  placeholder = "— Tìm hoặc chọn thuốc trong danh mục —",
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [extraMedications, setExtraMedications] = useState<MedicationDetail[]>([]);
  const [isSearchingApi, setIsSearchingApi] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number>(-1);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listboxId = useId();

  // Combine parent provided medications with any remote search results
  const allMedications = useMemo(() => {
    const map = new Map<string, MedicationDetail>();
    for (const m of medications) {
      map.set(m.id, m);
    }
    for (const m of extraMedications) {
      if (!map.has(m.id)) {
        map.set(m.id, m);
      }
    }
    return Array.from(map.values());
  }, [medications, extraMedications]);

  const selectedMedication = useMemo(
    () => allMedications.find((m) => m.id === selectedId) ?? null,
    [allMedications, selectedId],
  );

  // Filter medications based on search query
  const filteredMedications = useMemo(() => {
    const query = searchQuery.trim();
    if (!query) return allMedications;

    const normalizedQuery = normalizeText(query);
    const queryTokens = normalizedQuery.split(/\s+/).filter(Boolean);

    return allMedications.filter((m) => {
      const nameNorm = normalizeText(m.name || "");
      const compNorm = normalizeText(m.composition || "");
      const manuNorm = normalizeText(m.manufacturer || "");
      const usesNorm = normalizeText(m.uses || "");

      const fullText = `${nameNorm} ${compNorm} ${manuNorm} ${usesNorm}`;

      return queryTokens.every((token) => fullText.includes(token));
    });
  }, [allMedications, searchQuery]);

  // Debounced API search when typing a query
  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (trimmed.length < 2) {
      setIsSearchingApi(false);
      return;
    }

    let isCancelled = false;
    const timer = setTimeout(async () => {
      try {
        setIsSearchingApi(true);
        const result = await api.medications({ search: trimmed, size: 50 });
        if (!isCancelled && result.content) {
          setExtraMedications((prev) => {
            const existingIds = new Set(prev.map((item) => item.id));
            const newItems = result.content.filter((item) => !existingIds.has(item.id));
            return [...prev, ...newItems];
          });
        }
      } catch {
        // Fallback silently to client-side filtered results
      } finally {
        if (!isCancelled) {
          setIsSearchingApi(false);
        }
      }
    }, 300);

    return () => {
      isCancelled = true;
      clearTimeout(timer);
    };
  }, [searchQuery]);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen) {
      searchInputRef.current?.focus();
      setActiveIndex(-1);
    } else {
      setSearchQuery("");
      setActiveIndex(-1);
    }
  }, [isOpen]);

  // Scroll active item into view
  useEffect(() => {
    if (activeIndex >= 0 && listRef.current) {
      const activeEl = listRef.current.children[activeIndex] as HTMLElement;
      if (activeEl) {
        activeEl.scrollIntoView({ block: "nearest" });
      }
    }
  }, [activeIndex]);

  const handleOpen = () => {
    if (disabled) return;
    setIsOpen(true);
  };

  const handleSelect = (medication: MedicationDetail) => {
    onSelect(medication);
    setIsOpen(false);
    setSearchQuery("");
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelect(null);
    setSearchQuery("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev < filteredMedications.length - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => (prev > 0 ? prev - 1 : filteredMedications.length - 1));
    } else if (e.key === "Enter" && activeIndex >= 0 && activeIndex < filteredMedications.length) {
      e.preventDefault();
      handleSelect(filteredMedications[activeIndex]);
    }
  };

  return (
    <div
      className={`med-combobox ${isOpen ? "is-open" : ""} ${disabled ? "is-disabled" : ""}`}
      ref={containerRef}
      onKeyDown={handleKeyDown}
    >
      {/* Combobox Trigger */}
      <div
        className="med-combobox-trigger"
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        tabIndex={disabled ? -1 : 0}
        onClick={() => (isOpen ? setIsOpen(false) : handleOpen())}
      >
        <div className="med-combobox-trigger-content">
          {selectedMedication ? (
            <div className="med-selected-display">
              <span className="med-selected-name">{selectedMedication.name}</span>
              {selectedMedication.composition && (
                <span className="med-selected-sub"> · {selectedMedication.composition}</span>
              )}
            </div>
          ) : (
            <span className="med-combobox-placeholder">{placeholder}</span>
          )}
        </div>

        <div className="med-combobox-actions">
          {selectedMedication && !disabled && (
            <button
              type="button"
              className="med-combobox-clear"
              aria-label="Xóa chọn thuốc"
              title="Xóa lựa chọn"
              onClick={handleClear}
            >
              ✕
            </button>
          )}
          <span className={`med-combobox-chevron ${isOpen ? "open" : ""}`} aria-hidden="true">
            ▾
          </span>
        </div>
      </div>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="med-combobox-dropdown" role="presentation">
          {/* Search Box Header */}
          <div className="med-combobox-search-wrapper">
            <svg
              className="med-search-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref={searchInputRef}
              type="text"
              className="med-combobox-search-input"
              placeholder="Gõ tên thuốc, hoạt chất, biệt dược..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
            {searchQuery && (
              <button
                type="button"
                className="med-search-clear-btn"
                onClick={() => setSearchQuery("")}
                aria-label="Xóa tìm kiếm"
              >
                ✕
              </button>
            )}
          </div>

          {/* Status Header */}
          <div className="med-combobox-status">
            {isSearchingApi ? (
              <span className="med-status-text searching">Đang tìm trên hệ thống…</span>
            ) : searchQuery.trim() ? (
              <span className="med-status-text">
                Tìm thấy <b>{filteredMedications.length}</b> thuốc phù hợp
              </span>
            ) : (
              <span className="med-status-text">
                Danh mục: <b>{filteredMedications.length}</b> thuốc
              </span>
            )}
          </div>

          {/* Options List */}
          <ul
            id={listboxId}
            ref={listRef}
            className="med-combobox-list"
            role="listbox"
            aria-label="Danh mục thuốc"
          >
            {filteredMedications.length === 0 ? (
              <li className="med-combobox-empty" role="status">
                <span className="med-empty-title">Không tìm thấy thuốc phù hợp</span>
                <span className="med-empty-hint">
                  {searchQuery ? `Không có kết quả cho "${searchQuery}"` : "Danh mục trống"}
                </span>
              </li>
            ) : (
              filteredMedications.map((med, idx) => {
                const isSelected = med.id === selectedId;
                const isActive = idx === activeIndex;

                return (
                  <li
                    key={med.id}
                    id={`${listboxId}-opt-${med.id}`}
                    role="option"
                    aria-selected={isSelected}
                    className={`med-combobox-option ${isSelected ? "is-selected" : ""} ${
                      isActive ? "is-active" : ""
                    }`}
                    onClick={() => handleSelect(med)}
                    onMouseEnter={() => setActiveIndex(idx)}
                  >
                    <div className="med-option-main">
                      <div className="med-option-title-row">
                        <span className="med-option-name">{med.name}</span>
                        {med.source_name && <span className="med-option-badge">{med.source_name}</span>}
                      </div>
                      {med.composition && (
                        <div className="med-option-comp">
                          <span className="med-comp-label">Hoạt chất:</span> {med.composition}
                        </div>
                      )}
                      {med.uses && (
                        <div className="med-option-uses">
                          <span className="med-uses-label">Công dụng:</span> {med.uses}
                        </div>
                      )}
                    </div>
                    {isSelected && (
                      <span className="med-option-check" aria-hidden="true">
                        ✓
                      </span>
                    )}
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
