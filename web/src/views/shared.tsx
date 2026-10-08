import { useEffect, useState } from "react";

export const currency = (value: number) => `¥${value}`;
export function useLoad<T>(load: () => Promise<T>) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  useEffect(() => { let active = true; setState({ loading: true }); load().then((data) => active && setState({ data, loading: false }), (error: Error) => active && setState({ error: error.message, loading: false })); return () => { active = false; }; }, [load]);
  return state;
}
export function State({ loading, error, empty, children }: { loading: boolean; error?: string; empty?: boolean; children: React.ReactNode }) {
  if (loading) return <p>加载中…</p>; if (error) return <p role="alert">{error}</p>; if (empty) return <p>暂无数据</p>; return <>{children}</>;
}
