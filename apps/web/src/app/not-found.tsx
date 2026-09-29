import Link from "next/link";
import { EmptyState } from "@/components/ui";
export default function NotFound() { return <EmptyState title="This page isn’t here" action={<Link className="button primary" href="/">Back to overview</Link>}>Your purchase memory is still close by. Return to your overview to continue.</EmptyState>; }
