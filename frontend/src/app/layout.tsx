import type { Metadata, Viewport } from "next";
import { Inter, Playfair_Display, JetBrains_Mono } from "next/font/google";
import { AppProviders } from "@/components/AppProviders";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const playfair = Playfair_Display({ subsets: ["latin"], variable: "--font-playfair", display: "swap" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f2eb" },
    { media: "(prefers-color-scheme: dark)", color: "#0f0f11" },
  ],
  colorScheme: "light dark",
};

// The public site URL is deploy-specific; set NEXT_PUBLIC_SITE_URL at build
// time. It must never fall back to a placeholder domain — a leftover
// hackathon URL here used to leak into every og:url tag.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "";

export const metadata: Metadata = {
  title: {
    default: "Veyrune — A workspace that builds its own tools",
    template: "%s · Veyrune",
  },
  description:
    "Veyrune turns goals into reviewed, executable workflows and can build missing API tools along the way.",
  keywords: ["AI", "autonomous", "workspace", "agents", "MCP", "integrations", "automation"],
  ...(SITE_URL ? { metadataBase: new URL(SITE_URL) } : {}),
  openGraph: {
    title: "Veyrune — A workspace that builds its own tools",
    description: "Turn a goal into a workflow. Veyrune can build missing API tools, execute the work, and keep people in control.",
    type: "website",
    siteName: "Veyrune",
    ...(SITE_URL ? { url: SITE_URL } : {}),
  },
  twitter: {
    card: "summary_large_image",
    title: "Veyrune — A workspace that builds its own tools",
    description: "Turn a goal into a workflow. Veyrune can build missing API tools, execute the work, and keep people in control.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${playfair.variable} ${jetbrains.variable}`}>
      <body className="font-sans">
        {/* First-paint theme: apply before React hydrates to prevent flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('agentos_theme');if(t==='dark'||t==='light'){document.documentElement.setAttribute('data-theme',t)}}catch(e){}})()`,
          }}
        />
        <AppProviders>
          {children}
        </AppProviders>
      </body>
    </html>
  );
}
