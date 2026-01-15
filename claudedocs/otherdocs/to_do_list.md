# DocAI Project To-Do List

> **Last Updated**: 2025-12-05
> **Status Legend**:
> - [ ] Pending
> - [x] Completed
> - [~] In Progress

---

## High Priority

### Infrastructure & Architecture

- [ ] **Integrate ZeroMQ to system**
  - **Priority**: High
  - **Rationale**: Current skill_id collision fix works for single-machine, low-concurrency scenarios. For production-grade reliability with high concurrency or distributed deployment, ZeroMQ message queue will ensure:
    - Sequential task processing
    - No ID collisions under any circumstances
    - Graceful error handling and retry mechanisms
    - Better scalability for future growth
  - **Implementation Notes**:
    - Add `pyzmq` dependency
    - Create task queue for PDF upload processing
    - Implement worker pattern for background processing
    - Add monitoring and health checks

---

## Medium Priority

### Performance Optimization

- [ ] Implement master FAISS index per skill (reduce memory fragmentation)
- [ ] Add LRU cache for loaded skill indices
- [ ] Optimize vector search with relevance threshold filtering

### User Experience

- [ ] Add progress bar for PDF upload and processing
- [ ] Implement SSE (Server-Sent Events) for real-time response streaming
- [ ] Add multi-language support completion (full i18n coverage)

### Data Integrity

- [ ] Add database unique constraints to prevent duplicate entries
- [ ] Implement soft delete for skills and documents
- [ ] Add data backup and recovery mechanisms

---

## Low Priority

### Features

- [ ] Integrate OPMP (Optimistic Progressive Markdown Parsing) to Skill system
- [ ] Add skill versioning and history tracking
- [ ] Implement skill sharing and collaboration features

### Documentation

- [ ] Complete API documentation with Swagger/OpenAPI
- [ ] Create user manual for skill management
- [ ] Add architecture diagrams and flowcharts

### Testing

- [ ] Add unit tests for skill upload pipeline
- [ ] Implement integration tests for end-to-end workflows
- [ ] Add performance benchmarks and monitoring

---

## Completed

- [x] Fix sessionStorage race condition (chat history persistence) - 2025-12-05
- [x] Fix skill_id collision when uploading multiple files - 2025-12-05
- [x] Fix source_name showing as "Unknown" - 2025-12-05
- [x] Implement draggable sidebar resize - 2025-12-05
- [x] Update system logo - 2025-12-05
- [x] Add translation keys for stats display - 2025-12-05

---

## Notes

### ZeroMQ Integration Plan

```
Architecture:
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   FastAPI   │────►│   ZeroMQ    │────►│   Worker    │
│  (Producer) │     │   Queue     │     │  (Consumer) │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Result    │
                    │   Storage   │
                    └─────────────┘

Benefits:
- Guaranteed unique processing order
- No race conditions or ID collisions
- Scalable worker pool
- Fault tolerance with retry logic
```

---

*Maintained by: Development Team*
*Review Frequency: Weekly*
