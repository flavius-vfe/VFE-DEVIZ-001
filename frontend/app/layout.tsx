import "./globals.css";
export const metadata = {
  title: "VFE Deviz",
  description: "Devize de construcții și BOQ"
};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="ro"><body>{children}</body></html>;
}
