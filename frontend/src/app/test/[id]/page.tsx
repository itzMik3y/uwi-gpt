import { useSearchParams } from 'next/navigation'
const test = ()=>{
    const searchParams = useSearchParams()
    const search = searchParams.get('search')
    return (
        <div>
            
        </div>
    )
}