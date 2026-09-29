---
name: report-with-tally-table
description: 每批对局下完后，汇报里附一张总览表，列各组合各棋种已算数的局数、比分和关键指标
metadata:
  node_type: memory
  type: feedback
  originSessionId: 6735de81-360e-4311-b6f7-5c60ddf9b99e
  modified: 2026-09-29T10:49:45.952Z
---

每批对局下完，给用户汇报时附一张总览表，不只写本批结果：按「对阵组合 × 棋种」列出已算数的局数（只算带理由的新协议对局）、还差几局、比分（分先后手），以及每步平均亏损、大失误这类关键指标。

**Why:** 用户 2026-09-29 要求，想一眼看清当前整体进度，而不是从零散的每批汇报里自己拼。
**How to apply:** 每批收尾汇报都带这张表；目标是每个组合每种棋 4 局，参见 [[converge-infra-real-player]]。
