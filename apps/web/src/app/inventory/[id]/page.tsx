import { InventoryDetail } from "@/components/screens/inventory";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <InventoryDetail key={id} id={id} />; }
