/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DIFF_VIEWER_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
