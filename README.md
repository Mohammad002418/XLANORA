# XLANORA – Bilingual Service Marketplace

**XLANORA** is a bilingual (English & Arabic) online marketplace that connects customers with independent service providers. It makes discovering, comparing, and booking professional services simple, convenient, and accessible.

From photography and home maintenance to tutoring and other professional services, XLANORA provides a platform where customers can find trusted providers and manage their bookings.

## ✨ Key Features

### 👤 Customer Experience
- Secure user registration and authentication.
- Browse and search services by category, city, and price.
- View provider profiles, portfolios, and customer reviews.
- Book available appointment slots.
- Cancel existing bookings.
- Save favorite services to a personal wishlist.
- Bilingual interface supporting English and Arabic.

### 🛠️ Service Provider Dashboard
- Create and manage professional profiles.
- Publish services with descriptions and pricing.
- Set availability and working hours.
- Accept or reject customer bookings.
- Showcase previous work through photo and short-video portfolios.
- Manage bookings and service listings.

### 🔐 Admin Dashboard
- Manage customers and service providers.
- Moderate services, profiles, and platform content.
- Review and manage customer contact messages.
- Maintain platform quality and content standards.

### 💳 Payment System
- Direct payments between customers and service providers.
- No integrated payment gateway or platform payment processing.
- Prices displayed in Saudi Riyals (SAR), with estimated USD equivalents.
- Customers and providers coordinate payment directly.

### 📅 Booking Management
- Book available service time slots.
- Prevent double-booking through database-level constraints.
- Manage booking requests and their statuses.
- Support booking acceptance, rejection, and cancellation.

## 🏗️ Project Architecture

XLANORA includes two application versions:

### 1. Local Version – Python + SQLite
Designed for local development, testing, and experimentation.

- Python-based local server.
- SQLite database.
- Local data management.
- Suitable for development and debugging.

### 2. Supabase Version – Recommended for Production
Designed for deployment and public access.

- Supabase Authentication.
- PostgreSQL database.
- Supabase Storage for media files.
- Static frontend generated through a build script.
- Netlify hosting for public deployment.

## 🧰 Technology Stack

| Technology | Purpose |
|---|---|
| HTML, CSS, JavaScript | Frontend |
| Python | Local server |
| SQLite | Local database |
| Supabase | Authentication and backend services |
| PostgreSQL | Production database |
| Supabase Storage | Images and media |
| Netlify | Static website hosting |
| Git & GitHub | Version control |

## 🌍 Platform Goals

XLANORA aims to provide:

- A simple and accessible service-booking experience.
- Equal opportunities for independent service providers.
- Transparent service pricing.
- Flexible booking management.
- A bilingual experience for Arabic- and English-speaking users.
- A scalable foundation for future marketplace improvements.

## 🚀 Deployment

The Supabase version is the recommended version for public deployment.

The public frontend is generated using a build script and hosted on Netlify, while Supabase provides authentication, database services, and media storage.

The local SQLite version remains available for development and testing.

## 🧪 Testing Status

The project includes unit tests for important application functionality.

**Current status:** The latest test execution was interrupted before completion. Therefore, the full test suite has not yet been confirmed as passing after the latest documentation update.

## 📌 Project Status

XLANORA is an ongoing marketplace project focused on improving the customer booking experience, provider management, and platform reliability.

---

**XLANORA – Discover Services. Connect with Professionals. Book with Confidence.**
