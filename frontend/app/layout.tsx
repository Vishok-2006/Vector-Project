import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agentic RAG Assistant",
  description: "Upload PDFs and query them via Gemini and Endee.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen selection:bg-accent/30 selection:text-white">
        {children}
      </body>
    </html>
  );
}
