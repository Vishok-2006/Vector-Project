import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vectora - Chat with your PDFs",
  description: "Vectora: upload PDFs and get grounded answers, powered by NVIDIA NIM and Qdrant.",
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
