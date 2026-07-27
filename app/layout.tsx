import React from "react";
import type { Metadata } from "next";
import { Cal_Sans as FontHeading, Plus_Jakarta_Sans as FontSans } from "next/font/google";
import "./globals.css";

const fontSans = FontSans({
    subsets: ["latin"],
    variable: "--font-sans"
});

const fontHeading = FontHeading({
    subsets: ["latin"],
    variable: "--font-heading",
    weight: "400"
});

export const metadata: Metadata = {
  title: "Indofolk AI — a companion for older adults",
  description:
    "Indofolk AI is a companion for older adults in India, on WhatsApp. Voice-first, in Hindi and English. It remembers, reminds and answers — and never takes payments, never asks for an OTP, and never acts on your accounts.",
  metadataBase: new URL("https://n8nworld.store"),
  openGraph: {
    title: "Indofolk AI — a companion for older adults",
    description:
      "Voice-first. Hindi and English. Remembers, reminds, answers. Never transacts.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
          className={`${fontSans.variable} ${fontHeading.variable} font-sans antialiased`}
      >
        <div className="bg-pattern"></div>
        {children}
      </body>
    </html>
  );
}
