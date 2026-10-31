package com.coursepilot.verifier.persistence.repo;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

/** Pageable that represents the offset cursor used by the public API. */
public record OffsetPageRequest(int offset, int pageSize, Sort sort) implements Pageable {

    public OffsetPageRequest {
        if (offset < 0) throw new IllegalArgumentException("offset must be non-negative");
        if (pageSize < 1) throw new IllegalArgumentException("pageSize must be positive");
        sort = sort == null ? Sort.unsorted() : sort;
    }

    @Override public int getPageNumber() { return offset / pageSize; }
    @Override public int getPageSize() { return pageSize; }
    @Override public long getOffset() { return offset; }
    @Override public Sort getSort() { return sort; }
    @Override public Pageable next() { return new OffsetPageRequest(offset + pageSize, pageSize, sort); }
    @Override public Pageable previousOrFirst() {
        return hasPrevious() ? new OffsetPageRequest(Math.max(0, offset - pageSize), pageSize, sort) : first();
    }
    @Override public Pageable first() { return new OffsetPageRequest(0, pageSize, sort); }
    @Override public Pageable withPage(int pageNumber) {
        if (pageNumber < 0) throw new IllegalArgumentException("pageNumber must be non-negative");
        return new OffsetPageRequest(Math.multiplyExact(pageNumber, pageSize), pageSize, sort);
    }
    @Override public boolean hasPrevious() { return offset > 0; }
}
