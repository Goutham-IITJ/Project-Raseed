import { Assistant } from "@/components/screens/assistant";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <Assistant key={id} id={id} />; }
