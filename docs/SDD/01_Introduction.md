# AI-Radar

## Software Design Document (SDD)

**Version:** 2.0

**Status:** Draft

**Project Type:** AI-powered Knowledge Intelligence Platform

**Author:** Le Tuan Dat

---

# 1. Introduction

## 1.1 Project Overview

AI-Radar là một hệ thống tự động thu thập, xử lý, lưu trữ và khai thác tri thức từ nhiều nguồn thông tin về Trí tuệ Nhân tạo (Artificial Intelligence).

Khác với các chatbot truyền thống chỉ phản hồi khi người dùng đặt câu hỏi, AI-Radar được thiết kế như một nền tảng "Technology Intelligence". Hệ thống chủ động cập nhật tri thức mới theo lịch định kỳ, xây dựng một kho tri thức (Knowledge Base) và cung cấp hai phương thức tiếp cận thông tin:

* Chủ động gửi bản tin công nghệ hằng ngày (Daily Digest).
* Cho phép người dùng truy vấn kho tri thức thông qua cơ chế Retrieval-Augmented Generation (RAG).

Nói cách khác, AI-Radar không chỉ đơn thuần là một chatbot hay một công cụ tổng hợp RSS, mà là một hệ thống có khả năng liên tục học hỏi từ các nguồn dữ liệu mới và biến chúng thành tri thức có cấu trúc, phục vụ cả nhu cầu theo dõi tin tức và tra cứu kiến thức.

---

## 1.2 Motivation

Lĩnh vực AI đang phát triển với tốc độ rất nhanh.

Mỗi ngày xuất hiện:

* mô hình ngôn ngữ mới,
* framework mới,
* thư viện mã nguồn mở,
* bài nghiên cứu,
* bài blog kỹ thuật,
* benchmark,
* hướng dẫn triển khai,
* bài phân tích.

Một AI Engineer thường phải theo dõi đồng thời rất nhiều nguồn:

* Hugging Face
* Hacker News
* GitHub
* LangChain Blog
* Anthropic
* OpenAI
* Google AI
* Meta AI
* Microsoft Research
* Papers With Code
* arXiv
* Reddit
* Dev.to
* Medium

Việc đọc toàn bộ lượng thông tin này mỗi ngày gần như không khả thi.

Phần lớn thời gian bị tiêu tốn vào việc:

* tìm kiếm,
* lọc bỏ bài không liên quan,
* đọc tiêu đề,
* mở từng bài viết,
* so sánh nhiều nguồn.

Trong khi mục tiêu thực sự chỉ là trả lời các câu hỏi như:

* Hôm nay AI có gì mới?
* Có framework nào đáng chú ý?
* OCR hiện nay phát triển đến đâu?
* Có paper nào đáng đọc?
* Có model mới nên thử không?

AI-Radar ra đời nhằm giảm đáng kể thời gian tiếp cận tri thức bằng cách tự động hóa toàn bộ quy trình thu thập, phân tích và tổng hợp thông tin.

---

## 1.3 Vision

Tầm nhìn của AI-Radar không phải trở thành một chatbot đa năng.

Dự án hướng đến việc xây dựng một "AI Knowledge Companion" dành cho cá nhân.

Mọi tri thức về AI mà người dùng quan tâm đều được cập nhật liên tục vào một kho tri thức thống nhất.

Thay vì ghi nhớ:

> "Mình từng đọc bài đó ở đâu?"

Người dùng chỉ cần hỏi:

> OCR nào đang được đánh giá cao hiện nay?

hoặc

> LangGraph Memory hoạt động như thế nào?

Hệ thống sẽ tự động truy xuất các bài viết đã thu thập, tổng hợp và trả lời.

AI-Radar đóng vai trò như một "bộ nhớ thứ hai" (Second Brain) chuyên về AI.

---