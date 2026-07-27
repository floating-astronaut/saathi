import Link from "next/link";
import React from "react";

export function PolicyPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-200">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link
          href="/"
          className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
          ← Indofolk AI
        </Link>
        <h1 className="mt-6 font-heading text-4xl text-gray-900 dark:text-white">{title}</h1>
        <p className="mt-2 text-sm text-gray-500">Last updated {updated}</p>
        <div className="policy mt-10 space-y-6 leading-relaxed">{children}</div>
        <footer className="mt-16 border-t border-gray-200 pt-8 text-sm text-gray-500 dark:border-gray-800">
          <nav className="flex flex-wrap gap-x-6 gap-y-2">
            <Link href="/privacy/" className="hover:underline">Privacy</Link>
            <Link href="/terms/" className="hover:underline">Terms</Link>
            <Link href="/data-deletion/" className="hover:underline">Delete your data</Link>
          </nav>
        </footer>
      </div>
    </main>
  );
}

export function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="font-heading text-2xl text-gray-900 dark:text-white pt-4">{children}</h2>;
}

export function P({ children }: { children: React.ReactNode }) {
  return <p className="text-gray-700 dark:text-gray-300">{children}</p>;
}

export function UL({ children }: { children: React.ReactNode }) {
  return <ul className="list-disc space-y-2 pl-6 text-gray-700 dark:text-gray-300">{children}</ul>;
}
