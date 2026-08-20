import "./globals.css";
import Script from "next/script";
export const metadata = {
  title: "VFE Deviz",
  description: "Devize de construcții și BOQ"
};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="ro"><body><Script src="/runtime-config.js" strategy="beforeInteractive" />{children}</body></html>;
}
