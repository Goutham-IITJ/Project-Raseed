import { InsightDetail } from "@/components/screens/insights";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <InsightDetail key={id} id={id} />; }
