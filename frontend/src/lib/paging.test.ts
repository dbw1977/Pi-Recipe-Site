import { describe, expect, it } from 'vitest';
import {
  clampPage,
  DEFAULT_PAGE_SIZE,
  DEFAULT_SORT,
  pageCount,
  parsePageSize,
  parseSort,
  rangeText,
} from './paging';

describe('pageCount', () => {
  it('rounds up and never drops below one page', () => {
    expect(pageCount(0, 20)).toBe(1);
    expect(pageCount(20, 20)).toBe(1);
    expect(pageCount(21, 20)).toBe(2);
    expect(pageCount(100, 50)).toBe(2);
    expect(pageCount(101, 50)).toBe(3);
  });
});

describe('clampPage', () => {
  it('pulls an out-of-range page back in', () => {
    expect(clampPage(5, 45, 20)).toBe(2); // 45 recipes -> pages 0..2
    expect(clampPage(-3, 45, 20)).toBe(0);
    expect(clampPage(1, 45, 20)).toBe(1);
    expect(clampPage(4, 0, 20)).toBe(0);
  });
});

describe('rangeText', () => {
  it('describes the visible slice', () => {
    expect(rangeText(87, 0, 20)).toBe('1–20 of 87');
    expect(rangeText(87, 4, 20)).toBe('81–87 of 87'); // last page is short
    expect(rangeText(87, 1, 50)).toBe('51–87 of 87');
    expect(rangeText(0, 0, 20)).toBe('0 recipes');
    expect(rangeText(0, 0, 20, 'place')).toBe('0 places');
  });
});

describe('stored preferences', () => {
  it('only accepts the offered page sizes', () => {
    expect(parsePageSize('50')).toBe(50);
    expect(parsePageSize(100)).toBe(100);
    expect(parsePageSize('37')).toBe(DEFAULT_PAGE_SIZE);
    expect(parsePageSize(null)).toBe(DEFAULT_PAGE_SIZE);
  });
  it('only accepts known sorts (relevance is never stored)', () => {
    expect(parseSort('rating_desc')).toBe('rating_desc');
    expect(parseSort('relevance')).toBe(DEFAULT_SORT);
    expect(parseSort('bogus')).toBe(DEFAULT_SORT);
    expect(parseSort(null)).toBe(DEFAULT_SORT);
  });
});
