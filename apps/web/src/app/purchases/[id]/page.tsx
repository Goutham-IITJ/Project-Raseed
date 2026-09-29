import { PurchaseDetail } from "@/components/screens/purchase-detail";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <PurchaseDetail key={id} id={id} />; }
