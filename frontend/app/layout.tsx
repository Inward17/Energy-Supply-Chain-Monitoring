import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Archivo, IBM_Plex_Mono } from 'next/font/google'
import './globals.css'
import 'leaflet/dist/leaflet.css'
import { ThemeProvider } from '@/components/theme-provider'

const archivo = Archivo({
  variable: '--font-archivo',
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800', '900'],
  display: 'swap',
})

const plexMono = IBM_Plex_Mono({
  variable: '--font-plex-mono',
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  display: 'swap',
})

// Runs synchronously in <head> before first paint, so the correct theme class is
// on <html> before anything renders (no flash). Resolving system preference into
// a real class here — rather than via a prefers-color-scheme media block — is
// what keeps the CSS variables and the `dark:` variant from ever disagreeing.
const THEME_INIT_SCRIPT = `(function(){try{
var s=localStorage.getItem('meridian-theme');
var d=s?s==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;
var e=document.documentElement;
e.classList.toggle('dark',d);e.classList.toggle('light',!d);
e.style.colorScheme=d?'dark':'light';
}catch(_){document.documentElement.classList.add('dark')}})()`

export const metadata: Metadata = {
  title: 'Energy Supply Chain Resilience OS',
  description:
    'Command center for monitoring geopolitical risk, tracking crude oil vessels, and calculating supply chain reroutes.',
  generator: 'v0.app',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f4f2ee' },
    { media: '(prefers-color-scheme: dark)', color: '#0b0f16' },
  ],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${archivo.variable} ${plexMono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="font-sans antialiased">
        <ThemeProvider>{children}</ThemeProvider>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
