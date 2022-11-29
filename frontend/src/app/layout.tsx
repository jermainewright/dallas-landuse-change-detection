import type { Metadata } from "next";
import { Space_Grotesk, JetBrains_Mono, Inter } from "next/font/google";
import { Toaster } from "react-hot-toast";
import QueryProvider from "@/components/ui/QueryProvider";
import "./globals.css";

const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["300", "400", "500", "600", "700"],
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
});

const body = Inter({
  subsets: ["latin"],
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "Dallas LandScan · Land Use Change Detection",
  description:
    "Satellite imagery analysis and temporal land use change detection for Dallas, Texas. Powered by Landsat imagery, PostGIS, and machine learning classification.",
  keywords: ["remote sensing", "GIS", "Dallas", "land use", "change detection", "satellite"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${display.variable} ${mono.variable} ${body.variable} bg-void-950 text-slate-200 font-body antialiased`}
      >
        <QueryProvider>
          {children}
          <Toaster
            position="bottom-right"
            toastOptions={{
              style: {
                background: "#111829",
                color: "#e2e8f0",
                border: "1px solid rgba(0,229,204,0.2)",
                fontFamily: "var(--font-mono)",
                fontSize: "13px",
              },
            }}
          />
        </QueryProvider>
      </body>
    </html>
  );
}
